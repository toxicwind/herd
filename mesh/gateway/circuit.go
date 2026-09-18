package astmatrix

import (
	"sync"
	"time"
)

type CircuitState int
<<<<<<< HEAD
=======

>>>>>>> origin/main
const (
	StateClosed CircuitState = iota
	StateOpen
	StateHalfOpen
)

type CircuitBreaker struct {
<<<<<<< HEAD
	state          CircuitState
	failureCount   int
	successCount   int
	failureThreshold int
	halfOpenMaxCalls int
	timeout        time.Duration
	lastFailure    time.Time
	mu             sync.RWMutex
}

type CircuitRegistry struct {
	mu       sync.Mutex
	breakers map[string]*CircuitBreaker
	failureThreshold int
	timeout  time.Duration
=======
	state            CircuitState
	failureCount     int
	successCount     int
	failureThreshold int
	halfOpenMaxCalls int
	timeout          time.Duration
	lastFailure      time.Time
	mu               sync.RWMutex
}

type CircuitRegistry struct {
	mu               sync.Mutex
	breakers         map[string]*CircuitBreaker
	failureThreshold int
	timeout          time.Duration
>>>>>>> origin/main
}

func NewCircuitRegistry(failureThreshold int, timeout time.Duration) *CircuitRegistry {
	return &CircuitRegistry{
<<<<<<< HEAD
		breakers: make(map[string]*CircuitBreaker),
		failureThreshold: failureThreshold,
		timeout: timeout,
=======
		breakers:         make(map[string]*CircuitBreaker),
		failureThreshold: failureThreshold,
		timeout:          timeout,
>>>>>>> origin/main
	}
}

func (cr *CircuitRegistry) get(name string) *CircuitBreaker {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	cb, ok := cr.breakers[name]
	if !ok {
		cb = &CircuitBreaker{
<<<<<<< HEAD
			state: StateClosed,
			failureThreshold: cr.failureThreshold,
			halfOpenMaxCalls: 3,
			timeout: cr.timeout,
=======
			state:            StateClosed,
			failureThreshold: cr.failureThreshold,
			halfOpenMaxCalls: 3,
			timeout:          cr.timeout,
>>>>>>> origin/main
		}
		cr.breakers[name] = cb
	}
	return cb
}

<<<<<<< HEAD
func (cr *CircuitRegistry) Allow(name string) bool { return cr.get(name).Allow() }
=======
func (cr *CircuitRegistry) Allow(name string) bool    { return cr.get(name).Allow() }
>>>>>>> origin/main
func (cr *CircuitRegistry) RecordSuccess(name string) { cr.get(name).RecordSuccess() }
func (cr *CircuitRegistry) RecordFailure(name string) { cr.get(name).RecordFailure() }

func (cb *CircuitBreaker) Allow() bool {
	cb.mu.RLock()
	defer cb.mu.RUnlock()
	switch cb.state {
	case StateClosed:
		return true
	case StateOpen:
		if time.Since(cb.lastFailure) > cb.timeout {
			cb.mu.RUnlock()
			cb.mu.Lock()
			cb.state = StateHalfOpen
			cb.successCount = 0
			cb.mu.Unlock()
			cb.mu.RLock()
			return true
		}
		return false
	case StateHalfOpen:
		return cb.successCount < cb.halfOpenMaxCalls
	}
	return false
}

func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.successCount++
	switch cb.state {
	case StateHalfOpen:
		if cb.successCount >= cb.halfOpenMaxCalls {
			cb.state = StateClosed
			cb.failureCount = 0
			cb.successCount = 0
		}
	case StateClosed:
		cb.failureCount = 0
	}
}

func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.failureCount++
	cb.lastFailure = time.Now()
	switch cb.state {
	case StateHalfOpen:
		cb.state = StateOpen
		cb.successCount = 0
	case StateClosed:
		if cb.failureCount >= cb.failureThreshold {
			cb.state = StateOpen
		}
	}
}
