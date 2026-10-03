// Package gmrtdcompat hides API differences between the gmrtd pins the harness measures,
// so every driver builds against either pin from the same source.
//
// The default build targets gmrtd v1.1.3 (64bd6ab). Building with
// -tags gmrtd_8fea245 -modfile gomod/gmrtd-8fea245.mod targets v0.45.0 (8fea245), and
// -tags gmrtd_b861835 -modfile gomod/gmrtd-b861835.mod targets v1.3.2 (b861835).
// Commit is compiled in, so a run artifact names the gmrtd commit its binary was built
// against rather than whatever happens to be checked out at run time.
package gmrtdcompat
