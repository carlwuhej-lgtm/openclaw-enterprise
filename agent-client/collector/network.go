package collector

import (
	"context"
	"net"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// ConnectionInfo holds information about a network connection.
type ConnectionInfo struct {
	PID        int    `json:"pid"`
	LocalAddr  string `json:"local_addr"`
	RemoteAddr string `json:"remote_addr"`
	Status     string `json:"status"`
	IsLLMCall  bool   `json:"is_llm_call"`
	Provider   string `json:"provider"` // openai/anthropic/dashscope etc.
}

// llmDomains maps LLM API domains to provider names.
var llmDomains = map[string]string{
	"api.openai.com":          "openai",
	"api.anthropic.com":       "anthropic",
	"dashscope.aliyuncs.com":  "dashscope",
	"api.deepseek.com":        "deepseek",
	"api.moonshot.cn":         "moonshot",
	"open.bigmodel.cn":        "zhipu",
	"api.cohere.ai":           "cohere",
	"api.mistral.ai":          "mistral",
	"generativelanguage.googleapis.com": "google",
	"api.groq.com":            "groq",
	"api.together.xyz":        "together",
	"api.replicate.com":       "replicate",
	"api.fireworks.ai":        "fireworks",
	"api.perplexity.ai":       "perplexity",
	"api.baichuan-ai.com":     "baichuan",
	"api.minimax.chat":        "minimax",
	"aip.baidubce.com":        "baidu",
	"api.siliconflow.cn":      "siliconflow",
}

// llmIPs caches resolved IPs for LLM domains.
var llmIPs map[string]string

// resolveLLMIPs resolves LLM domain names to IPs for matching.
// Uses goroutines with timeout to avoid blocking on DNS failures.
func resolveLLMIPs() map[string]string {
	if llmIPs != nil {
		return llmIPs
	}
	llmIPs = make(map[string]string)

	type result struct {
		domain   string
		provider string
		addrs    []string
	}

	ch := make(chan result, len(llmDomains))
	for domain, provider := range llmDomains {
		go func(d, p string) {
			resolver := &net.Resolver{}
			ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
			defer cancel()
			addrs, err := resolver.LookupHost(ctx, d)
			if err != nil {
				ch <- result{d, p, nil}
				return
			}
			ch <- result{d, p, addrs}
		}(domain, provider)
	}

	for i := 0; i < len(llmDomains); i++ {
		r := <-ch
		for _, addr := range r.addrs {
			llmIPs[addr] = r.provider
		}
	}
	return llmIPs
}

// matchLLMProvider checks if a remote address belongs to an LLM provider.
func matchLLMProvider(remoteAddr string) (bool, string) {
	// Extract host (without port)
	host := remoteAddr
	if h, _, err := net.SplitHostPort(remoteAddr); err == nil {
		host = h
	}

	// Direct IP match
	ips := resolveLLMIPs()
	if provider, ok := ips[host]; ok {
		return true, provider
	}

	// Try reverse DNS lookup
	names, err := net.LookupAddr(host)
	if err == nil {
		for _, name := range names {
			name = strings.TrimSuffix(name, ".")
			for domain, provider := range llmDomains {
				if strings.HasSuffix(name, domain) || name == domain {
					return true, provider
				}
			}
		}
	}

	return false, ""
}

// CollectConnections scans network connections.
func CollectConnections() ([]ConnectionInfo, error) {
	switch runtime.GOOS {
	case "linux":
		return collectConnectionsLinux()
	case "windows":
		return collectConnectionsWindows()
	default:
		return collectConnectionsNetstat()
	}
}

// collectConnectionsNetstat uses netstat for macOS and other Unix systems.
func collectConnectionsNetstat() ([]ConnectionInfo, error) {
	out, err := exec.Command("/usr/sbin/netstat", "-an", "-p", "tcp").Output()
	if err != nil {
		// macOS may need different flags
		out, err = exec.Command("/usr/sbin/netstat", "-an").Output()
		if err != nil {
			return nil, err
		}
	}

	var connections []ConnectionInfo
	lines := strings.Split(string(out), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || !strings.Contains(line, "ESTABLISHED") {
			continue
		}

		fields := strings.Fields(line)
		if len(fields) < 5 {
			continue
		}

		// Find local and remote address fields
		// Typical netstat output: Proto Recv-Q Send-Q Local Foreign State
		var localAddr, remoteAddr, status string
		if fields[0] == "tcp" || fields[0] == "tcp4" || fields[0] == "tcp6" {
			if len(fields) >= 6 {
				localAddr = fields[3]
				remoteAddr = fields[4]
				status = fields[5]
			} else {
				localAddr = fields[3]
				remoteAddr = fields[4]
				status = "ESTABLISHED"
			}
		} else {
			continue
		}

		isLLM, provider := matchLLMProvider(remoteAddr)

		// Only report LLM connections or connections on common HTTPS port
		if isLLM {
			connections = append(connections, ConnectionInfo{
				LocalAddr:  localAddr,
				RemoteAddr: remoteAddr,
				Status:     status,
				IsLLMCall:  isLLM,
				Provider:   provider,
			})
		}
	}

	return connections, nil
}

// collectConnectionsLinux reads /proc/net/tcp for connection info.
func collectConnectionsLinux() ([]ConnectionInfo, error) {
	// Fall back to netstat/ss on Linux too for simplicity
	out, err := exec.Command("ss", "-tnp").Output()
	if err != nil {
		return collectConnectionsNetstat()
	}

	var connections []ConnectionInfo
	lines := strings.Split(string(out), "\n")
	for i, line := range lines {
		if i == 0 { // skip header
			continue
		}
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}

		fields := strings.Fields(line)
		if len(fields) < 5 {
			continue
		}

		// ss output: State Recv-Q Send-Q Local:Port Peer:Port Process
		status := fields[0]
		localAddr := fields[3]
		remoteAddr := fields[4]

		pid := 0
		if len(fields) >= 6 {
			// Parse PID from "users:(("name",pid=123,fd=4))"
			procField := fields[5]
			if idx := strings.Index(procField, "pid="); idx >= 0 {
				pidStr := procField[idx+4:]
				if end := strings.IndexAny(pidStr, ",)"); end >= 0 {
					pid, _ = strconv.Atoi(pidStr[:end])
				}
			}
		}

		isLLM, provider := matchLLMProvider(remoteAddr)
		if isLLM {
			connections = append(connections, ConnectionInfo{
				PID:        pid,
				LocalAddr:  localAddr,
				RemoteAddr: remoteAddr,
				Status:     status,
				IsLLMCall:  isLLM,
				Provider:   provider,
			})
		}
	}

	return connections, nil
}

// collectConnectionsWindows uses netstat on Windows.
func collectConnectionsWindows() ([]ConnectionInfo, error) {
	out, err := exec.Command("netstat", "-ano").Output()
	if err != nil {
		return nil, err
	}

	var connections []ConnectionInfo
	lines := strings.Split(string(out), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || !strings.Contains(line, "ESTABLISHED") {
			continue
		}

		fields := strings.Fields(line)
		if len(fields) < 5 {
			continue
		}

		// Windows netstat -ano: Proto Local Remote State PID
		if fields[0] != "TCP" {
			continue
		}

		localAddr := fields[1]
		remoteAddr := fields[2]
		status := fields[3]
		pid, _ := strconv.Atoi(fields[4])

		isLLM, provider := matchLLMProvider(remoteAddr)
		if isLLM {
			connections = append(connections, ConnectionInfo{
				PID:        pid,
				LocalAddr:  localAddr,
				RemoteAddr: remoteAddr,
				Status:     status,
				IsLLMCall:  isLLM,
				Provider:   provider,
			})
		}
	}

	return connections, nil
}
