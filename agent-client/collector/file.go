package collector

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"time"
)

// FileEvent holds information about a file system event.
type FileEvent struct {
	Path      string `json:"path"`
	Operation string `json:"operation"` // read/write/delete
	Timestamp string `json:"timestamp"`
	ProcessID int    `json:"process_id"`
}

// FileMonitor monitors sensitive directories for changes.
type FileMonitor struct {
	mu         sync.Mutex
	events     []FileEvent
	mtimeCache map[string]time.Time
	existCache map[string]bool
}

// NewFileMonitor creates a new file monitor.
func NewFileMonitor() *FileMonitor {
	return &FileMonitor{
		mtimeCache: make(map[string]time.Time),
		existCache: make(map[string]bool),
	}
}

// sensitivePaths returns OS-specific sensitive paths to monitor.
func sensitivePaths() []string {
	home, _ := os.UserHomeDir()
	paths := []string{
		filepath.Join(home, ".ssh"),
		filepath.Join(home, ".gnupg"),
		filepath.Join(home, ".aws"),
		filepath.Join(home, ".azure"),
		filepath.Join(home, ".gcloud"),
		filepath.Join(home, ".kube"),
		filepath.Join(home, ".docker"),
		filepath.Join(home, ".env"),
		filepath.Join(home, ".gitconfig"),
		filepath.Join(home, ".npmrc"),
		filepath.Join(home, ".pypirc"),
	}

	switch runtime.GOOS {
	case "linux":
		paths = append(paths,
			"/etc/shadow",
			"/etc/passwd",
			"/etc/sudoers",
			"/etc/hosts",
		)
	case "darwin":
		paths = append(paths,
			"/etc/hosts",
			filepath.Join(home, "Library/Keychains"),
		)
	case "windows":
		paths = append(paths,
			`C:\Windows\System32\config\SAM`,
			`C:\Windows\System32\drivers\etc\hosts`,
		)
	}

	return paths
}

// Scan checks all sensitive paths for changes since last scan.
func (fm *FileMonitor) Scan() []FileEvent {
	fm.mu.Lock()
	defer fm.mu.Unlock()

	var newEvents []FileEvent
	now := time.Now().UTC().Format(time.RFC3339)

	for _, path := range sensitivePaths() {
		fm.scanPath(path, now, &newEvents)
	}

	return newEvents
}

// scanPath checks a single path (file or directory) for changes.
func (fm *FileMonitor) scanPath(path string, timestamp string, events *[]FileEvent) {
	info, err := os.Stat(path)
	if err != nil {
		// File/dir doesn't exist
		if fm.existCache[path] {
			// Was there before, now deleted
			*events = append(*events, FileEvent{
				Path:      path,
				Operation: "delete",
				Timestamp: timestamp,
			})
			delete(fm.existCache, path)
			delete(fm.mtimeCache, path)
		}
		return
	}

	fm.existCache[path] = true

	if info.IsDir() {
		// Scan directory entries
		entries, err := os.ReadDir(path)
		if err != nil {
			return
		}
		for _, entry := range entries {
			entryPath := filepath.Join(path, entry.Name())
			fm.scanFile(entryPath, timestamp, events)
		}
	} else {
		fm.scanFile(path, timestamp, events)
	}
}

// scanFile checks a single file for mtime changes.
func (fm *FileMonitor) scanFile(path string, timestamp string, events *[]FileEvent) {
	info, err := os.Stat(path)
	if err != nil {
		if fm.existCache[path] {
			*events = append(*events, FileEvent{
				Path:      path,
				Operation: "delete",
				Timestamp: timestamp,
			})
			delete(fm.existCache, path)
			delete(fm.mtimeCache, path)
		}
		return
	}

	mtime := info.ModTime()
	prevMtime, exists := fm.mtimeCache[path]

	if !exists {
		// First time seeing this file, record but don't report
		fm.mtimeCache[path] = mtime
		fm.existCache[path] = true
		return
	}

	if mtime.After(prevMtime) {
		// File was modified
		*events = append(*events, FileEvent{
			Path:      path,
			Operation: "write",
			Timestamp: timestamp,
		})
		fm.mtimeCache[path] = mtime
	}
}

// FlushEvents returns accumulated events and clears the buffer.
func (fm *FileMonitor) FlushEvents() []FileEvent {
	fm.mu.Lock()
	defer fm.mu.Unlock()
	events := fm.events
	fm.events = nil
	return events
}

// String returns a human-readable summary of a FileEvent.
func (e FileEvent) String() string {
	return fmt.Sprintf("[%s] %s: %s", e.Timestamp, e.Operation, e.Path)
}
