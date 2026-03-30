package collector

import (
	"os/exec"
	"runtime"
	"strconv"
	"strings"
)

// ProcessInfo holds information about a running process.
type ProcessInfo struct {
	PID     int     `json:"pid"`
	Name    string  `json:"name"`
	CmdLine string  `json:"cmdline"`
	CPU     float64 `json:"cpu"`
	Memory  float64 `json:"memory"`
	IsAgent bool    `json:"is_agent"` // Whether this is an AI Agent process
}

// agentKeywords are process names/keywords that indicate AI agent processes.
var agentKeywords = []string{
	"openclaw",
	"cursor",
	"claude",
	"copilot",
	"windsurf",
	"cline",
	"aider",
	"continue",
	"tabnine",
	"codeium",
	"amazon-q",
}

// agentCmdKeywords are command-line keywords for detecting agent-related processes.
var agentCmdKeywords = []string{
	"openclaw",
	".openclaw",
	"agent",
	"langchain",
	"autogen",
	"crewai",
	"openai",
	"anthropic",
	"claude",
	"cursor",
	"copilot",
	"windsurf",
	"cline",
}

// isAgentProcess checks if a process is an AI agent process.
func isAgentProcess(name, cmdline string) bool {
	nameLower := strings.ToLower(name)
	cmdLower := strings.ToLower(cmdline)

	// Check process name against known agent names
	for _, kw := range agentKeywords {
		if strings.Contains(nameLower, kw) {
			return true
		}
	}

	// Special check: node process with .openclaw in cmdline
	if nameLower == "node" && strings.Contains(cmdLower, ".openclaw") {
		return true
	}

	// Special check: python process with agent-related keywords
	if nameLower == "python" || nameLower == "python3" {
		for _, kw := range agentCmdKeywords {
			if strings.Contains(cmdLower, kw) {
				return true
			}
		}
	}

	return false
}

// CollectProcesses scans the process list and returns info about running processes.
func CollectProcesses() ([]ProcessInfo, error) {
	switch runtime.GOOS {
	case "windows":
		return collectProcessesWindows()
	default:
		return collectProcessesUnix()
	}
}

// collectProcessesUnix uses ps to collect process info on macOS/Linux.
func collectProcessesUnix() ([]ProcessInfo, error) {
	// ps output: PID %CPU %MEM COMMAND
	out, err := exec.Command("ps", "axo", "pid,%cpu,%mem,command").Output()
	if err != nil {
		return nil, err
	}

	var processes []ProcessInfo
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
		if len(fields) < 4 {
			continue
		}

		pid, err := strconv.Atoi(fields[0])
		if err != nil {
			continue
		}
		cpu, _ := strconv.ParseFloat(fields[1], 64)
		mem, _ := strconv.ParseFloat(fields[2], 64)
		cmdline := strings.Join(fields[3:], " ")

		// Extract process name from the command path
		name := fields[3]
		if idx := strings.LastIndex(name, "/"); idx >= 0 {
			name = name[idx+1:]
		}

		isAgent := isAgentProcess(name, cmdline)

		// Only include agent processes or processes with significant resource usage
		if isAgent || cpu > 5.0 {
			processes = append(processes, ProcessInfo{
				PID:     pid,
				Name:    name,
				CmdLine: truncateString(cmdline, 512),
				CPU:     cpu,
				Memory:  mem,
				IsAgent: isAgent,
			})
		}
	}

	return processes, nil
}

// collectProcessesWindows uses tasklist/wmic to collect process info on Windows.
func collectProcessesWindows() ([]ProcessInfo, error) {
	out, err := exec.Command("tasklist", "/FO", "CSV", "/V").Output()
	if err != nil {
		// Fallback to simple tasklist
		out, err = exec.Command("tasklist", "/FO", "CSV").Output()
		if err != nil {
			return nil, err
		}
	}

	var processes []ProcessInfo
	lines := strings.Split(string(out), "\n")
	for i, line := range lines {
		if i == 0 { // skip header
			continue
		}
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}

		// Parse CSV: "Name","PID","Session Name","Session#","Mem Usage",...
		fields := parseCSVLine(line)
		if len(fields) < 5 {
			continue
		}

		name := strings.Trim(fields[0], "\"")
		pid, err := strconv.Atoi(strings.Trim(fields[1], "\""))
		if err != nil {
			continue
		}

		isAgent := isAgentProcess(name, name)

		if isAgent {
			processes = append(processes, ProcessInfo{
				PID:     pid,
				Name:    name,
				CmdLine: name,
				IsAgent: isAgent,
			})
		}
	}

	return processes, nil
}

// parseCSVLine does a simple CSV line parse (handles quoted fields).
func parseCSVLine(line string) []string {
	var fields []string
	var field strings.Builder
	inQuote := false
	for _, r := range line {
		switch {
		case r == '"':
			inQuote = !inQuote
		case r == ',' && !inQuote:
			fields = append(fields, field.String())
			field.Reset()
		default:
			field.WriteRune(r)
		}
	}
	fields = append(fields, field.String())
	return fields
}

// truncateString truncates a string to maxLen.
func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
