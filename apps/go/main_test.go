package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"runtime"
	"strconv"
	"testing"
)

// The medians below were computed by hand from the LCG in medianOfSorted
// (x = x*6364136223846793005 + 1442695040888963407 mod 2^64, seed 42): the
// first five values are 10481999410520546993, 4159066171780167020,
// 7615522811268512075, 11628791489956661374, 12546512532490043765, so n=3
// sorts to [4159..., 7615..., 10481...] and n=5 puts 10481... in the middle.
func TestEcho(t *testing.T) {
	tests := []struct {
		name       string
		query      string
		status     int
		wantN      int64
		wantMedian uint64
		checkValue bool
	}{
		{"zero", "n=0", http.StatusOK, 0, 0, true},
		{"three", "n=3", http.StatusOK, 3, 7615522811268512075, true},
		{"five", "n=5", http.StatusOK, 5, 10481999410520546993, true},
		{"maxN is accepted", "n=1000000", http.StatusOK, maxN, 0, false},
		{"missing", "", http.StatusBadRequest, 0, 0, false},
		{"not a number", "n=abc", http.StatusBadRequest, 0, 0, false},
		{"negative", "n=-1", http.StatusBadRequest, 0, 0, false},
		{"maxN+1 is rejected", "n=1000001", http.StatusBadRequest, 0, 0, false},
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
			if got.N != tc.wantN || (tc.checkValue && got.Median != tc.wantMedian) {
				t.Fatalf("got %+v, want n=%d median=%d", got, tc.wantN, tc.wantMedian)
			}
		})
	}
}

// Sizes k6 might ask for, to calibrate runner/k6/go.js ECHO_N:
//   go test -bench Median -run '^$'
func BenchmarkMedian(b *testing.B) {
	for _, n := range []int{1_000, 5_000, 10_000, 20_000} {
		b.Run(strconv.Itoa(n), func(b *testing.B) {
			for b.Loop() {
				medianOfSorted(n)
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
