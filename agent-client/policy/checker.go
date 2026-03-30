package policy

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/openclaw-enterprise/agent-client/collector"
)

// ServerPolicy is the format returned by the management platform API.
type ServerPolicy struct {
	ID     int                    `json:"id"`
	Name   string                 `json:"name"`
	Config map[string]interface{} `json:"config"`
}

// Policy defines a security policy rule (internal format).
type Policy struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Type        string `json:"type"`        // process_block, network_block, file_alert
	Pattern     string `json:"pattern"`     // Pattern to match
	Action      string `json:"action"`      // alert, block, log
	Description string `json:"description"`
	Enabled     bool   `json:"enabled"`
}

// PolicySet holds a collection of policies.
type PolicySet struct {
	Policies  []Policy  `json:"policies"`
	UpdatedAt time.Time `json:"updated_at"`
}

// Alert represents a policy violation alert.
type Alert struct {
	PolicyID    string `json:"policy_id"`
	PolicyName  string `json:"policy_name"`
	Type        string `json:"type"`
	Description string `json:"description"`
	Detail      string `json:"detail"`
	Timestamp   string `json:"timestamp"`
	Severity    string `json:"severity"` // low, medium, high, critical
}

// Checker manages policy checking.
type Checker struct {
	serverURL  string
	policies   PolicySet
	mu         sync.RWMutex
	client     *http.Client
	cacheFile  string
	lastFetch  time.Time
	fetchInterval time.Duration
	enforcer   *Enforcer
}

// NewChecker creates a new policy checker.
func NewChecker(serverURL string) *Checker {
	home, _ := os.UserHomeDir()
	cacheFile := filepath.Join(home, ".openclaw-enterprise", "policies.json")

	c := &Checker{
		serverURL: serverURL,
		client: &http.Client{
			Timeout: 5 * time.Second,
		},
		cacheFile:     cacheFile,
		fetchInterval: 5 * time.Minute,
		enforcer:      NewEnforcer(),
	}

	// Load cached policies
	c.loadCache()

	return c
}

// GetEnforcer 获取执行器
func (c *Checker) GetEnforcer() *Enforcer {
	return c.enforcer
}

// FetchPolicies fetches policies from the management platform.
func (c *Checker) FetchPolicies() error {
	// Rate limit: don't fetch too frequently
	if time.Since(c.lastFetch) < c.fetchInterval {
		return nil
	}

	url := c.serverURL + "/api/client/policies"
	resp, err := c.client.Get(url)
	if err != nil {
		return fmt.Errorf("fetch policies: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("server returned status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read response: %w", err)
	}

	var policies PolicySet

	// API 返回数组格式 [{id, name, config}, ...]
	var serverPolicies []ServerPolicy
	if err := json.Unmarshal(body, &serverPolicies); err != nil {
		return fmt.Errorf("parse policies: %w", err)
	}

	// 转换为内部格式
	for _, sp := range serverPolicies {
		// 从 config 中提取 paths → file_alert
		if paths, ok := sp.Config["paths"]; ok {
			if pathList, ok := paths.([]interface{}); ok {
				for _, p := range pathList {
					policies.Policies = append(policies.Policies, Policy{
						ID:      fmt.Sprintf("%d", sp.ID),
						Name:    sp.Name,
						Type:    "file_alert",
						Pattern: fmt.Sprintf("%v", p),
						Action:  "alert",
						Enabled: true,
					})
				}
			}
		}
		// 从 config 中提取 commands → process_block
		if cmds, ok := sp.Config["commands"]; ok {
			if cmdList, ok := cmds.([]interface{}); ok {
				for _, cmd := range cmdList {
					policies.Policies = append(policies.Policies, Policy{
						ID:      fmt.Sprintf("%d", sp.ID),
						Name:    sp.Name,
						Type:    "process_block",
						Pattern: fmt.Sprintf("%v", cmd),
						Action:  "block",
						Enabled: true,
					})
				}
			}
		}
	}
	policies.UpdatedAt = time.Now()

	c.mu.Lock()
	c.policies = policies
	c.lastFetch = time.Now()
	c.mu.Unlock()

	c.saveCache()
	return nil
}

// CheckProcesses checks processes against policies and enforces blocks.
func (c *Checker) CheckProcesses(processes []collector.ProcessInfo) []Alert {
	c.mu.RLock()
	defer c.mu.RUnlock()

	var alerts []Alert
	now := time.Now().UTC().Format(time.RFC3339)

	for _, policy := range c.policies.Policies {
		if !policy.Enabled || policy.Type != "process_block" {
			continue
		}

		for _, proc := range processes {
			pattern := strings.ToLower(policy.Pattern)
			if strings.Contains(strings.ToLower(proc.Name), pattern) ||
				strings.Contains(strings.ToLower(proc.CmdLine), pattern) {
				
				alert := Alert{
					PolicyID:    policy.ID,
					PolicyName:  policy.Name,
					Type:        "process_violation",
					Description: policy.Description,
					Detail:      fmt.Sprintf("Process %q (PID %d) matches blocked pattern %q", proc.Name, proc.PID, policy.Pattern),
					Timestamp:   now,
					Severity:    "high",
				}
				alerts = append(alerts, alert)

				// 执行阻断
				if c.enforcer != nil && policy.Action == "block" {
					rule := BlockRule{
						PolicyID:   policy.ID,
						PolicyName: policy.Name,
						Type:       "process",
						Pattern:    policy.Pattern,
						Action:     "terminate",
						Severity:   "high",
					}
					report := c.enforcer.EnforceProcess(proc, rule)
					c.enforcer.SendReport(report)
				}
			}
		}
	}

	return alerts
}

// CheckConnections checks network connections against policies.
func (c *Checker) CheckConnections(connections []collector.ConnectionInfo) []Alert {
	c.mu.RLock()
	defer c.mu.RUnlock()

	var alerts []Alert
	now := time.Now().UTC().Format(time.RFC3339)

	for _, policy := range c.policies.Policies {
		if !policy.Enabled || policy.Type != "network_block" {
			continue
		}

		for _, conn := range connections {
			pattern := strings.ToLower(policy.Pattern)
			if strings.Contains(strings.ToLower(conn.RemoteAddr), pattern) ||
				strings.Contains(strings.ToLower(conn.Provider), pattern) {
				alerts = append(alerts, Alert{
					PolicyID:    policy.ID,
					PolicyName:  policy.Name,
					Type:        "network_violation",
					Description: policy.Description,
					Detail:      fmt.Sprintf("Connection to %s (provider: %s) matches blocked pattern %q", conn.RemoteAddr, conn.Provider, policy.Pattern),
					Timestamp:   now,
					Severity:    "high",
				})
			}
		}
	}

	return alerts
}

// CheckFileEvents checks file events against policies.
func (c *Checker) CheckFileEvents(events []collector.FileEvent) []Alert {
	c.mu.RLock()
	defer c.mu.RUnlock()

	var alerts []Alert
	now := time.Now().UTC().Format(time.RFC3339)

	for _, policy := range c.policies.Policies {
		if !policy.Enabled || policy.Type != "file_alert" {
			continue
		}

		for _, event := range events {
			pattern := strings.ToLower(policy.Pattern)
			if strings.Contains(strings.ToLower(event.Path), pattern) {
				alerts = append(alerts, Alert{
					PolicyID:    policy.ID,
					PolicyName:  policy.Name,
					Type:        "file_violation",
					Description: policy.Description,
					Detail:      fmt.Sprintf("File %s was %s, matches alert pattern %q", event.Path, event.Operation, policy.Pattern),
					Timestamp:   now,
					Severity:    "medium",
				})
			}
		}
	}

	return alerts
}

// SendAlerts sends alerts to the management platform.
func (c *Checker) SendAlerts(agentID string, alerts []Alert) error {
	if len(alerts) == 0 {
		return nil
	}

	payload := struct {
		AgentID string  `json:"agent_id"`
		Alerts  []Alert `json:"alerts"`
	}{
		AgentID: agentID,
		Alerts:  alerts,
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	url := c.serverURL + "/api/alerts"
	resp, err := c.client.Post(url, "application/json", strings.NewReader(string(data)))
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, resp.Body)

	return nil
}

// loadCache loads cached policies from disk.
func (c *Checker) loadCache() {
	data, err := os.ReadFile(c.cacheFile)
	if err != nil {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	_ = json.Unmarshal(data, &c.policies)
}

// saveCache saves policies to disk.
func (c *Checker) saveCache() {
	c.mu.RLock()
	data, _ := json.Marshal(c.policies)
	c.mu.RUnlock()

	dir := filepath.Dir(c.cacheFile)
	_ = os.MkdirAll(dir, 0755)
	_ = os.WriteFile(c.cacheFile, data, 0644)
}
