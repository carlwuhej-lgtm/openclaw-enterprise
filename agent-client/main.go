package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/openclaw-enterprise/agent-client/collector"
	"github.com/openclaw-enterprise/agent-client/config"
	"github.com/openclaw-enterprise/agent-client/policy"
	"github.com/openclaw-enterprise/agent-client/reporter"
)

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		log.Printf("Warning: config issue: %v", err)
	}

	if cfg.ServerURL == "" {
		fmt.Fprintln(os.Stderr, "Error: --server is required (management platform address)")
		fmt.Fprintln(os.Stderr, "Usage: ocw-agent --server http://192.168.1.100:8000")
		os.Exit(1)
	}

	log.Printf("OpenClaw Enterprise Agent Client starting...")
	log.Printf("  Agent ID:  %s", cfg.AgentID)
	log.Printf("  Hostname:  %s", cfg.Hostname)
	log.Printf("  Server:    %s", cfg.ServerURL)
	log.Printf("  Interval:  %ds", cfg.Interval)
	log.Printf("  Config:    %s", cfg.ConfigFile)

	// Initialize components
	rpt := reporter.NewReporter(cfg.ServerURL)
	fileMonitor := collector.NewFileMonitor()
	policyChecker := policy.NewChecker(cfg.ServerURL)

	// Set up graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// Initial file scan to populate baseline
	fileMonitor.Scan()

	// Create ticker for periodic collection
	ticker := time.NewTicker(time.Duration(cfg.Interval) * time.Second)
	defer ticker.Stop()

	log.Println("Agent started. Press Ctrl+C to stop.")

	// Run first collection immediately
	collect(cfg, rpt, fileMonitor, policyChecker)

	// Main loop
	for {
		select {
		case <-ticker.C:
			collect(cfg, rpt, fileMonitor, policyChecker)
		case sig := <-sigChan:
			log.Printf("Received signal %v, shutting down gracefully...", sig)
			return
		}
	}
}

// collect performs one collection cycle: gather data, check policies, and report.
func collect(cfg *config.Config, rpt *reporter.Reporter, fm *collector.FileMonitor, pc *policy.Checker) {
	log.Println("Collecting data...")

	// Collect process info
	processes, err := collector.CollectProcesses()
	if err != nil {
		log.Printf("Warning: process collection failed: %v", err)
	}

	// Collect network connections
	connections, err := collector.CollectConnections()
	if err != nil {
		log.Printf("Warning: network collection failed: %v", err)
	}

	// Scan for file events
	fileEvents := fm.Scan()

	// Collect system info
	sysInfo := reporter.CollectSystemInfo()

	// Fetch policies (rate-limited internally)
	if err := pc.FetchPolicies(); err != nil {
		log.Printf("Warning: policy fetch failed: %v", err)
	}

	// Check policies locally
	var allAlerts []policy.Alert
	allAlerts = append(allAlerts, pc.CheckProcesses(processes)...)
	allAlerts = append(allAlerts, pc.CheckConnections(connections)...)
	allAlerts = append(allAlerts, pc.CheckFileEvents(fileEvents)...)

	// Send alerts if any
	if len(allAlerts) > 0 {
		log.Printf("Found %d policy violations, sending alerts...", len(allAlerts))
		if err := pc.SendAlerts(cfg.AgentID, allAlerts); err != nil {
			log.Printf("Warning: failed to send alerts: %v", err)
		}
	}

	// Build and send report
	report := reporter.Report{
		AgentID:     cfg.AgentID,
		Hostname:    cfg.Hostname,
		OS:          config.OSName(),
		Timestamp:   time.Now().UTC().Format(time.RFC3339),
		Processes:   processes,
		Connections: connections,
		FileEvents:  fileEvents,
		SystemInfo:  sysInfo,
	}

	agentCount := 0
	for _, p := range processes {
		if p.IsAgent {
			agentCount++
		}
	}

	if err := rpt.Send(report); err != nil {
		log.Printf("Warning: report send failed (cached for retry): %v", err)
	} else {
		log.Printf("Report sent: %d processes (%d agents), %d LLM connections, %d file events",
			len(processes), agentCount, len(connections), len(fileEvents))
	}
}
