---
title: Custom Shell Function for Quick Disk Usage Monitoring
tags: shell, diskusage, productivity
complexity: low
summary: Adds a custom shell function to quickly monitor disk usage in human-readable format.
---

## When to use
Use this skill when you frequently need to check the disk usage of directories and files at a glance. It provides quick access to detailed information about space consumption.

## Approach
Create a custom shell function `duh` that uses the `du -sh */* .[^.]* 2>/dev/null | sort -rh` command for a quick overview of directory and file sizes in human-readable format. This can be added directly into your user profile preferences using shell_exec.

## Example
```shell
function duh() { du -sh */* .[^.]* 2>/dev/null | sort -rh; }
```
This example demonstrates how to define the `duh` function, enhancing your productivity by providing a quick way to monitor disk usage.

## Pitfalls
Ensure that the new alias does not conflict with existing commands or aliases in your environment.
alias np='ping'
alias nt='traceroute'
function l() { ls -alh "$@"; }
function ni() { ifconfig "$@"; }
function fsl() { du -sh */* .[^.]* 2>/dev/null | sort -rh; }