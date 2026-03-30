package reporter

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"time"

	"github.com/openclaw-enterprise/agent-client/collector"
)

// Report is the data payload sent to the management platform.
type Report struct {
	AgentID     string                    `json:"agent_id"`
	Hostname    string                    `json:"hostname"`
	OS          string                    `json:"os"`
	Timestamp   string                    `json:"timestamp"`
	Processes   []collector.ProcessInfo   `json:"processes"`
	Connections []collector.ConnectionInfo `json:"connections"`
	FileEvents  []collector.FileEvent     `json:"file_events"`
	SystemInfo  SystemInfo                `json:"system_info"`
}

// SystemInfo holds basic system information.
type SystemInfo struct {
	OS       string  `json:"os"`
	Arch     string  `json:"arch"`
	Hostname string  `json:"hostname"`
	IP       string  `json:"ip"`
	CPUUsage float64 `json:"cpu_usage"`
	MemTotal uint64  `json:"mem_total"`
	MemUsed  uint64  `json:"mem_used"`
}

// Reporter handles sending reports to the management platform.
type Reporter struct {
	serverURL string
	client    *http.Client
	cache     []Report
	cacheMu   sync.Mutex
	cacheFile string
}

// NewReporter creates a new reporter.
func NewReporter(serverURL string) *Reporter {
	home, _ := os.UserHomeDir()
	cacheFile := filepath.Join(home, ".openclaw-enterprise", "report_cache.json")

	r := &Reporter{
		serverURL: serverURL,
		client: &http.Client{
			Timeout: 5 * time.Second,
		},
		cacheFile: cacheFile,
	}

	// Load cached reports from disk
	r.loadCache()

	return r
}

// Send sends a report to the management platform.
func (r *Reporter) Send(report Report) error {
	// Try to send cached reports first
	r.retryCached()

	data, err := json.Marshal(report)
	if err != nil {
		return fmt.Errorf("marshal report: %w", err)
	}

	url := r.serverURL + "/api/client/report"
	resp, err := r.client.Post(url, "application/json", bytes.NewReader(data))
	if err != nil {
		// Network error, cache the report
		r.cacheReport(report)
		return fmt.Errorf("send report: %w", err)
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, resp.Body)

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		r.cacheReport(report)
		return fmt.Errorf("server returned status %d", resp.StatusCode)
	}

	return nil
}

// cacheReport stores a failed report for retry.
func (r *Reporter) cacheReport(report Report) {
	r.cacheMu.Lock()
	defer r.cacheMu.Unlock()

	// Limit cache size to 100 reports
	if len(r.cache) >= 100 {
		r.cache = r.cache[1:]
	}
	r.cache = append(r.cache, report)
	r.saveCache()
}

// retryCached attempts to send cached reports.
func (r *Reporter) retryCached() {
	r.cacheMu.Lock()
	if len(r.cache) == 0 {
		r.cacheMu.Unlock()
		return
	}
	cached := make([]Report, len(r.cache))
	copy(cached, r.cache)
	r.cache = nil
	r.cacheMu.Unlock()

	var failed []Report
	for _, report := range cached {
		data, err := json.Marshal(report)
		if err != nil {
			continue
		}

		url := r.serverURL + "/api/client/report"
		resp, err := r.client.Post(url, "application/json", bytes.NewReader(data))
		if err != nil {
			failed = append(failed, report)
			continue
		}
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()

		if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
			failed = append(failed, report)
		}
	}

	if len(failed) > 0 {
		r.cacheMu.Lock()
		r.cache = append(failed, r.cache...)
		r.cacheMu.Unlock()
	}

	r.saveCache()
}

// loadCache loads cached reports from disk.
func (r *Reporter) loadCache() {
	data, err := os.ReadFile(r.cacheFile)
	if err != nil {
		return
	}
	r.cacheMu.Lock()
	defer r.cacheMu.Unlock()
	_ = json.Unmarshal(data, &r.cache)
}

// saveCache saves cached reports to disk.
func (r *Reporter) saveCache() {
	r.cacheMu.Lock()
	data, _ := json.Marshal(r.cache)
	r.cacheMu.Unlock()

	dir := filepath.Dir(r.cacheFile)
	_ = os.MkdirAll(dir, 0755)
	_ = os.WriteFile(r.cacheFile, data, 0644)
}

// CollectSystemInfo gathers basic system information.
func CollectSystemInfo() SystemInfo {
	hostname, _ := os.Hostname()

	return SystemInfo{
		OS:       runtime.GOOS,
		Arch:     runtime.GOARCH,
		Hostname: hostname,
		IP:       getLocalIP(),
		MemTotal: getMemTotal(),
		MemUsed:  getMemUsed(),
	}
}

// getLocalIP returns the primary local IP address.
func getLocalIP() string {
	addrs, err := net.InterfaceAddrs()
	if err != nil {
		return "unknown"
	}
	for _, addr := range addrs {
		if ipnet, ok := addr.(*net.IPNet); ok && !ipnet.IP.IsLoopback() {
			if ipnet.IP.To4() != nil {
				return ipnet.IP.String()
			}
		}
	}
	return "unknown"
}

// getMemTotal returns total memory in bytes (best effort).
func getMemTotal() uint64 {
	switch runtime.GOOS {
	case "linux":
		return readMemInfoValue("/proc/meminfo", "MemTotal")
	default:
		return 0
	}
}

// getMemUsed returns used memory in bytes (best effort).
func getMemUsed() uint64 {
	switch runtime.GOOS {
	case "linux":
		total := readMemInfoValue("/proc/meminfo", "MemTotal")
		available := readMemInfoValue("/proc/meminfo", "MemAvailable")
		if total > 0 && available > 0 {
			return total - available
		}
		return 0
	default:
		return 0
	}
}

// readMemInfoValue reads a specific value from /proc/meminfo.
func readMemInfoValue(path, key string) uint64 {
	data, err := os.ReadFile(path)
	if err != nil {
		return 0
	}
	for _, line := range bytes.Split(data, []byte("\n")) {
		if bytes.HasPrefix(line, []byte(key+":")) {
			fields := bytes.Fields(line)
			if len(fields) >= 2 {
				val := uint64(0)
				for _, b := range fields[1] {
					if b >= '0' && b <= '9' {
						val = val*10 + uint64(b-'0')
					}
				}
				// Convert from kB to bytes
				if len(fields) >= 3 && string(fields[2]) == "kB" {
					val *= 1024
				}
				return val
			}
		}
	}
	return 0
}
