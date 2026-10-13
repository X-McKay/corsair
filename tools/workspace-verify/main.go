// Trusted operator workspace verifier (SPEC-0070): reads, never imports or executes, workspace content, and
// reports every entry under the root as JSON; the host decides. It is uploaded into each sandbox next to the
// tree, so no image needs an interpreter. argv: root, maximum entries, maximum file bytes. An absent root
// reports exists=false. The output is the same document the former Python verifier printed, plus the SHA-256
// of this executable as read through /proc/self/exe.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"syscall"
)

// imode is Python's stat.S_IMODE: the permission bits with setuid, setgid and sticky, as the reference reports.
func imode(mode uint32) uint32 { return mode & 0o7777 }

func digest(r io.Reader, limit int64) (int64, string) {
	h := sha256.New()
	n, _ := io.Copy(h, io.LimitReader(r, limit))
	return n, hex.EncodeToString(h.Sum(nil))
}

func fail(message string) {
	os.Stderr.WriteString(message + "\n")
	os.Exit(2)
}

func main() {
	if len(os.Args) != 4 {
		fail("usage: verify ROOT LIMIT CAP")
	}
	root := os.Args[1]
	limit, err1 := strconv.Atoi(os.Args[2])
	capBytes, err2 := strconv.ParseInt(os.Args[3], 10, 64)
	if err1 != nil || err2 != nil || limit < 1 || capBytes < 1 {
		fail("bounded integer limits required")
	}
	out := map[string]any{"euid": os.Geteuid()}
	if self, err := os.Open("/proc/self/exe"); err == nil {
		_, out["verifier_sha256"] = digest(self, 1<<30)
		self.Close()
	}
	info, err := os.Lstat(root)
	out["exists"] = err == nil
	if err != nil {
		if !os.IsNotExist(err) {
			fail(err.Error())
		}
		emit(out)
		return
	}
	resolved, _ := filepath.EvalSymlinks(root)
	stat := info.Sys().(*syscall.Stat_t)
	out["root"] = []any{imode(stat.Mode), stat.Uid, info.IsDir(), resolved == root}
	files, dirs, other, count, truncated := map[string]any{}, map[string]any{}, []string{}, 0, false
	if info.IsDir() {
		var walk func(dir string) bool
		walk = func(dir string) bool {
			entries, err := os.ReadDir(dir)
			if err != nil {
				fail(err.Error())
			}
			// The former verifier's order: subdirectories first, then the rest, each sorted by name.
			sort.SliceStable(entries, func(i, j int) bool {
				if entries[i].IsDir() != entries[j].IsDir() {
					return entries[i].IsDir()
				}
				return entries[i].Name() < entries[j].Name()
			})
			var subdirs []string
			for _, entry := range entries {
				count++
				if count > limit {
					truncated = true
					return false
				}
				path := filepath.Join(dir, entry.Name())
				rel, _ := filepath.Rel(root, path)
				st, err := os.Lstat(path)
				if err != nil {
					fail(err.Error())
				}
				sys := st.Sys().(*syscall.Stat_t)
				switch {
				case st.Mode().IsDir():
					dirs[rel] = []any{imode(sys.Mode), sys.Uid}
					subdirs = append(subdirs, path)
				case st.Mode().IsRegular():
					fd, err := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
					if err != nil {
						fail(err.Error())
					}
					f := os.NewFile(uintptr(fd), path)
					var t syscall.Stat_t
					if err := syscall.Fstat(fd, &t); err != nil {
						fail(err.Error())
					}
					if t.Mode&syscall.S_IFMT != syscall.S_IFREG {
						// Replaced between the walk and the open: report what was opened, never read it as a file.
						f.Close()
						other = append(other, rel)
						continue
					}
					size, sum := digest(f, capBytes+1)
					f.Close()
					files[rel] = []any{imode(t.Mode), t.Uid, t.Nlink, size, sum}
				default:
					other = append(other, rel)
				}
			}
			for _, sub := range subdirs {
				if !walk(sub) {
					return false
				}
			}
			return true
		}
		walk(root)
	}
	out["files"], out["directories"], out["other"], out["truncated"] = files, dirs, other, truncated
	emit(out)
}

func emit(out map[string]any) {
	data, err := json.Marshal(out)
	if err != nil {
		fail(err.Error())
	}
	os.Stdout.Write(append(data, '\n'))
}
