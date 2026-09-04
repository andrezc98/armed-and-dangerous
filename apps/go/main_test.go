package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"runtime"
	"testing"
)

func TestEcho(t *testing.T) {
	tests := []struct {
		name    string
		query   string
		status  int
		wantN   int64
		wantSum int64
	}{
		{"zero", "n=0", http.StatusOK, 0, 0},
		{"ten", "n=10", http.StatusOK, 10, 55},
		{"missing", "", http.StatusBadRequest, 0, 0},
		{"not a number", "n=abc", http.StatusBadRequest, 0, 0},
		{"negative", "n=-1", http.StatusBadRequest, 0, 0},
		{"too large", "n=10000001", http.StatusBadRequest, 0, 0},
	}
	srv := httptest.NewServer(newMux())
	defer srv.Close()

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			resp, err := http.Get(srv.URL + "/api/echo?" + tc.query)
			if err != nil {
				t.Fatal(err)
			}
			defer resp.Body.Close()
			if resp.StatusCode != tc.status {
				t.Fatalf("status = %d, want %d", resp.StatusCode, tc.status)
			}
			if tc.status != http.StatusOK {
				return
			}
			var got echoResponse
			if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
				t.Fatal(err)
			}
			if got.N != tc.wantN || got.Sum != tc.wantSum {
				t.Fatalf("got %+v, want n=%d sum=%d", got, tc.wantN, tc.wantSum)
			}
		})
	}
}

// The runner reads this endpoint through the API server service proxy as the
// cpuset control of the go cell, so the count has to be the process's own
// (15 vCPU on a 4xlarge with the static CPU manager, 7 on x86-smtoff), not a
// constant and not the node's.
func TestHealthz(t *testing.T) {
	rec := httptest.NewRecorder()
	newMux().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	var got healthResponse
	if err := json.NewDecoder(rec.Body).Decode(&got); err != nil {
		t.Fatal(err)
	}
	if got.CPUs != runtime.NumCPU() {
		t.Fatalf("cpus = %d, want %d", got.CPUs, runtime.NumCPU())
	}
}
