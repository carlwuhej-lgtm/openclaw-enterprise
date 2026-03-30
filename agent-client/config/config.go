package config

import (
	"crypto/rand"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
)

// Config holds the agent client configuration.
type Config struct {
	ServerURL  string `json:"server_url"`  // Management platform address
	AgentID    string `json:"agent_id"`    // Unique client identifier (auto-generated UUID)
	Hostname   string `json:"hostname"`    // Local hostname
	Interval   int    `json:"interval"`    // Collection interval (seconds)
	ConfigFile string `json:"-"`           // Config file path (not persisted)
}

// DefaultConfigDir returns the default configuration directory.
func DefaultConfigDir() string {
	home, err := os.UserHomeDir()
	if err != nil {
		home = "."
	}
	return filepath.Join(home, ".openclaw-enterprise")
}

// DefaultConfigFile returns the default config file path.
func DefaultConfigFile() string {
	return filepath.Join(DefaultConfigDir(), "agent.json")
}

// generateUUID generates a random UUID v4.
func generateUUID() string {
	uuid := make([]byte, 16)
	_, _ = rand.Read(uuid)
	uuid[6] = (uuid[6] & 0x0f) | 0x40 // version 4
	uuid[8] = (uuid[8] & 0x3f) | 0x80 // variant 10
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		uuid[0:4], uuid[4:6], uuid[6:8], uuid[8:10], uuid[10:16])
}

// Load reads config from file, applies command-line overrides, and saves if needed.
func Load() (*Config, error) {
	// Define command-line flags
	serverFlag := flag.String("server", "", "Management platform address (e.g. http://192.168.1.100:8000)")
	intervalFlag := flag.Int("interval", 0, "Report interval in seconds (default 30)")
	configFlag := flag.String("config", "", "Config file path")
	flag.Parse()

	// Determine config file path
	configFile := DefaultConfigFile()
	if *configFlag != "" {
		configFile = *configFlag
	}

	cfg := &Config{
		Interval:   30,
		ConfigFile: configFile,
	}

	// Try to load existing config file
	if data, err := os.ReadFile(configFile); err == nil {
		_ = json.Unmarshal(data, cfg)
	}

	// Apply command-line overrides
	if *serverFlag != "" {
		cfg.ServerURL = *serverFlag
	}
	if *intervalFlag > 0 {
		cfg.Interval = *intervalFlag
	}

	// Auto-generate AgentID if empty
	if cfg.AgentID == "" {
		cfg.AgentID = generateUUID()
	}

	// Auto-detect hostname
	hostname, err := os.Hostname()
	if err != nil {
		hostname = "unknown"
	}
	cfg.Hostname = hostname

	// Ensure config file path is set
	cfg.ConfigFile = configFile

	// Save config file
	if err := cfg.Save(); err != nil {
		return cfg, fmt.Errorf("failed to save config: %w", err)
	}

	return cfg, nil
}

// Save writes the config to disk.
func (c *Config) Save() error {
	dir := filepath.Dir(c.ConfigFile)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(c.ConfigFile, data, 0644)
}

// OSName returns the current OS name.
func OSName() string {
	return runtime.GOOS
}
