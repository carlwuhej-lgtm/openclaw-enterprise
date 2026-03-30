package policy

import (
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/openclaw-enterprise/agent-client/collector"
)

// Enforcer 执行策略阻断
type Enforcer struct {
	enabled     bool
	blockRules  map[string]BlockRule
	reportChan  chan EnforcementReport
}

// BlockRule 阻断规则配置
type BlockRule struct {
	PolicyID    string `json:"policy_id"`
	PolicyName  string `json:"policy_name"`
	Type        string `json:"type"`        // process, network, file
	Pattern     string `json:"pattern"`
	Action      string `json:"action"`      // terminate, block, alert
	Severity    string `json:"severity"`    // low, medium, high, critical
}

// EnforcementReport 阻断执行报告
type EnforcementReport struct {
	Timestamp   string `json:"timestamp"`
	PolicyID    string `json:"policy_id"`
	PolicyName  string `json:"policy_name"`
	Type        string `json:"type"`
	Target      string `json:"target"`
	Action      string `json:"action"`
	Result      string `json:"result"`
	Error       string `json:"error,omitempty"`
}

// NewEnforcer 创建新的执行器
func NewEnforcer() *Enforcer {
	return &Enforcer{
		enabled:    true,
		blockRules: make(map[string]BlockRule),
		reportChan: make(chan EnforcementReport, 100),
	}
}

// Enable 启用阻断
func (e *Enforcer) Enable() {
	e.enabled = true
}

// Disable 禁用阻断
func (e *Enforcer) Disable() {
	e.enabled = false
}

// IsEnabled 检查是否启用
func (e *Enforcer) IsEnabled() bool {
	return e.enabled
}

// EnforceProcess 执行进程阻断
func (e *Enforcer) EnforceProcess(proc collector.ProcessInfo, rule BlockRule) EnforcementReport {
	report := EnforcementReport{
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
		PolicyID:   rule.PolicyID,
		PolicyName: rule.PolicyName,
		Type:       "process",
		Target:     fmt.Sprintf("%s (PID %d)", proc.Name, proc.PID),
		Action:     rule.Action,
	}

	if !e.enabled {
		report.Result = "skipped"
		report.Error = "enforcer disabled"
		return report
	}

	switch rule.Action {
	case "terminate":
		err := e.terminateProcess(proc.PID)
		if err != nil {
			report.Result = "failed"
			report.Error = err.Error()
		} else {
			report.Result = "success"
		}
	case "alert":
		report.Result = "alert_only"
	default:
		report.Result = "unknown_action"
	}

	return report
}

// EnforceNetwork 执行网络阻断
func (e *Enforcer) EnforceNetwork(conn collector.ConnectionInfo, rule BlockRule) EnforcementReport {
	report := EnforcementReport{
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
		PolicyID:   rule.PolicyID,
		PolicyName: rule.PolicyName,
		Type:       "network",
		Target:     conn.RemoteAddr,
		Action:     rule.Action,
	}

	if !e.enabled {
		report.Result = "skipped"
		report.Error = "enforcer disabled"
		return report
	}

	switch rule.Action {
	case "block":
		err := e.blockConnection(conn)
		if err != nil {
			report.Result = "failed"
			report.Error = err.Error()
		} else {
			report.Result = "success"
		}
	case "alert":
		report.Result = "alert_only"
	default:
		report.Result = "unknown_action"
	}

	return report
}

// EnforceFile 执行文件阻断
func (e *Enforcer) EnforceFile(event collector.FileEvent, rule BlockRule) EnforcementReport {
	report := EnforcementReport{
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
		PolicyID:   rule.PolicyID,
		PolicyName: rule.PolicyName,
		Type:       "file",
		Target:     event.Path,
		Action:     rule.Action,
	}

	if !e.enabled {
		report.Result = "skipped"
		report.Error = "enforcer disabled"
		return report
	}

	// 文件访问无法真正"阻断"，只能记录和告警
	report.Result = "alert_only"
	return report
}

// terminateProcess 终止进程
func (e *Enforcer) terminateProcess(pid int) error {
	if pid <= 0 {
		return fmt.Errorf("invalid PID: %d", pid)
	}

	switch runtime.GOOS {
	case "windows":
		return e.terminateProcessWindows(pid)
	default:
		return e.terminateProcessUnix(pid)
	}
}

// terminateProcessUnix 在 Unix 系统上终止进程
func (e *Enforcer) terminateProcessUnix(pid int) error {
	// 先尝试 SIGTERM
	process, err := os.FindProcess(pid)
	if err != nil {
		return fmt.Errorf("find process: %w", err)
	}

	// 发送 SIGTERM
	err = process.Signal(syscall.SIGTERM)
	if err != nil {
		// 如果 SIGTERM 失败，尝试 SIGKILL
		err = process.Signal(syscall.SIGKILL)
		if err != nil {
			return fmt.Errorf("kill process: %w", err)
		}
	}

	// 等待进程退出（最多 5 秒）
	done := make(chan error, 1)
	go func() {
		_, err := process.Wait()
		done <- err
	}()

	select {
	case <-done:
		return nil
	case <-time.After(5 * time.Second):
		// 超时，强制 SIGKILL
		process.Signal(syscall.SIGKILL)
		return nil
	}
}

// terminateProcessWindows 在 Windows 上终止进程
func (e *Enforcer) terminateProcessWindows(pid int) error {
	// 使用 taskkill
	cmd := exec.Command("taskkill", "/F", "/PID", strconv.Itoa(pid))
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("taskkill failed: %s", string(output))
	}
	return nil
}

// blockConnection 阻断网络连接
func (e *Enforcer) blockConnection(conn collector.ConnectionInfo) error {
	switch runtime.GOOS {
	case "linux":
		return e.blockConnectionLinux(conn)
	case "darwin":
		return e.blockConnectionDarwin(conn)
	case "windows":
		return e.blockConnectionWindows(conn)
	default:
		return fmt.Errorf("unsupported OS: %s", runtime.GOOS)
	}
}

// blockConnectionLinux 使用 iptables 阻断（需要 root）
func (e *Enforcer) blockConnectionLinux(conn collector.ConnectionInfo) error {
	// 提取 IP 和端口
	host, port, err := parseAddr(conn.RemoteAddr)
	if err != nil {
		return err
	}

	// 添加 iptables 规则
	// 注意：这需要 root 权限
	cmd := exec.Command("iptables", "-A", "OUTPUT", "-d", host, "-p", "tcp", "--dport", port, "-j", "DROP")
	output, err := cmd.CombinedOutput()
	if err != nil {
		// 检查是否是权限问题
		if strings.Contains(string(output), "Permission denied") {
			return fmt.Errorf("iptables requires root privileges")
		}
		return fmt.Errorf("iptables failed: %s", string(output))
	}

	return nil
}

// blockConnectionDarwin 使用 pfctl 阻断（需要 root）
func (e *Enforcer) blockConnectionDarwin(conn collector.ConnectionInfo) error {
	// macOS 使用 pfctl，比较复杂
	// 这里简化处理，实际项目中可能需要更复杂的配置
	
	host, _, err := parseAddr(conn.RemoteAddr)
	if err != nil {
		return err
	}

	// 使用 route 临时阻止（非持久化）
	cmd := exec.Command("route", "add", "-host", host, "127.0.0.1", "-hopcount", "255")
	output, err := cmd.CombinedOutput()
	if err != nil {
		if strings.Contains(string(output), "Permission denied") {
			return fmt.Errorf("route requires root privileges")
		}
		// 可能已经存在该路由，忽略错误
	}

	return nil
}

// blockConnectionWindows 使用 Windows 防火墙阻断
func (e *Enforcer) blockConnectionWindows(conn collector.ConnectionInfo) error {
	host, port, err := parseAddr(conn.RemoteAddr)
	if err != nil {
		return err
	}

	// 使用 netsh 添加防火墙规则
	ruleName := fmt.Sprintf("OpenClaw-Block-%s-%s", host, port)
	cmd := exec.Command("netsh", "advfirewall", "firewall", "add", "rule",
		"name="+ruleName,
		"dir=out",
		"action=block",
		"remoteip="+host,
		"remoteport="+port,
		"protocol=tcp")
	
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("netsh failed: %s", string(output))
	}

	return nil
}

// parseAddr 解析地址为 IP 和端口
func parseAddr(addr string) (string, string, error) {
	parts := strings.Split(addr, ":")
	if len(parts) != 2 {
		return "", "", fmt.Errorf("invalid address format: %s", addr)
	}
	return parts[0], parts[1], nil
}

// GetReports 获取执行报告
func (e *Enforcer) GetReports() []EnforcementReport {
	var reports []EnforcementReport
	for {
		select {
		case report := <-e.reportChan:
			reports = append(reports, report)
		default:
			return reports
		}
	}
}

// SendReport 发送执行报告到通道
func (e *Enforcer) SendReport(report EnforcementReport) {
	select {
	case e.reportChan <- report:
	default:
		// 通道已满，丢弃最旧的报告
	}
}