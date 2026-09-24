// Go baseline for ARMed and Dangerous: a stdlib net/http JSON service with a
// small amount of real work per request (allocate, fill, sort, pick). It is the "silent baseline" cell: the
// workload class where silicon should barely matter (spec section 4).
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"runtime"
	"slices"
	"strconv"
)

// maxN bounds the per-request slice: every request allocates 8 bytes per
// element, so 1e6 is 8 MB of garbage per call at most. The load generator
// controls the rate, not the request size (runner/k6/go.js sets n).
const maxN = 1_000_000

type echoResponse struct {
	N      int64  `json:"n"`
	Median uint64 `json:"median"`
}

// healthResponse doubles as the cpuset control for this cell. The image is
// distroless, so the runner cannot `kubectl exec` a `cat
// /sys/fs/cgroup/cpuset.cpus.effective` into it the way it does for the other
// workloads; runtime.NumCPU() "returns the number of logical CPUs usable by the
// current process", i.e. it honours the affinity mask the static CPU manager
// set, so the server reports it itself and the runner reads it through the API
// server service proxy (runner/cell.py check_cpuset).
type healthResponse struct {
	CPUs int `json:"cpus"`
}

// medianOfSorted fills n values from a 64-bit LCG (Knuth's MMIX constants,
// fixed seed, so every request with the same n does the same work and returns
// the same answer), sorts them with slices.Sort and returns the upper median,
// s[n/2]; 0 for n = 0.
//
// Why not the old 1+2+...+n loop: a dependent add chain is one instruction per
// iteration, a microbenchmark of the adder that says nothing about a server.
// This one allocates, writes memory, branches on data (pdqsort) and makes the
// GC work, which is what a JSON service's request path looks like.
func medianOfSorted(n int) uint64 {
	if n == 0 {
		return 0
	}
	s := make([]uint64, n)
	x := uint64(42)
	for i := range s {
		x = x*6364136223846793005 + 1442695040888963407
		s[i] = x
	}
	slices.Sort(s)
	return s[n/2]
}

func echoHandler(w http.ResponseWriter, r *http.Request) {
	n, err := strconv.ParseInt(r.URL.Query().Get("n"), 10, 64)
	if err != nil || n < 0 || n > maxN {
		http.Error(w, `{"error":"n must be an integer in [0, 1000000]"}`, http.StatusBadRequest)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(echoResponse{N: n, Median: medianOfSorted(int(n))}); err != nil {
		log.Printf("encode: %v", err)
	}
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(healthResponse{CPUs: runtime.NumCPU()}); err != nil {
		log.Printf("encode: %v", err)
	}
}

func newMux() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/echo", echoHandler)
	mux.HandleFunc("GET /healthz", healthHandler)
	return mux
}

func main() {
	addr := ":" + envOr("PORT", "8080")
	log.Printf("aad-go listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, newMux()))
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
