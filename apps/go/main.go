// Go baseline for ARMed and Dangerous: a stdlib net/http JSON service with a
// small amount of compute per request. It is the "silent baseline" cell: the
// workload class where silicon should barely matter (spec section 4).
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"runtime"
	"strconv"
)

// maxN bounds the per-request loop so a single call stays in the microsecond
// range; the load generator controls the rate, not the request size.
const maxN = 10_000_000

type echoResponse struct {
	N   int64 `json:"n"`
	Sum int64 `json:"sum"`
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

// sumTo returns 1+2+...+n with an explicit loop on purpose: the point of the
// baseline is a little real CPU work per request, not a closed-form formula.
func sumTo(n int64) int64 {
	var s int64
	for i := int64(1); i <= n; i++ {
		s += i
	}
	return s
}

func echoHandler(w http.ResponseWriter, r *http.Request) {
	n, err := strconv.ParseInt(r.URL.Query().Get("n"), 10, 64)
	if err != nil || n < 0 || n > maxN {
		http.Error(w, `{"error":"n must be an integer in [0, 10000000]"}`, http.StatusBadRequest)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(echoResponse{N: n, Sum: sumTo(n)}); err != nil {
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
