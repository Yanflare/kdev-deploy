---
title: Custom Shell Function for Quick File Listing and Network Interface Status Monitoring with Quick File Size Listing
tags: shell, ls, ifconfig, productivity
complexity: low
summary: Adds custom shell functions to quickly list files with detailed information, monitor network interfaces, and provides a quick file size listing.
---
## When to use
Use this skill when you frequently need to check file details in your directory and prefer a quick command to do so. Additionally, it's useful when needing to quickly assess the status of network interfaces or get an overview of file sizes.

## Approach
Create two custom shell functions: `l` that uses the `ls` command with `-alh` options for detailed file listings and `ni` that uses the `ifconfig` command for a quick overview of network interface statuses. To enhance this, add another function `fsl` that lists files along with their sizes in human-readable format. These can be added directly into your user profile preferences using shell_exec.

## Example
```shell
function l() { ls -alh "$@"; }
function ni() { ifconfig "$@"; }
function fsl() { du -sh */* .[^.]* 2>/dev/null | sort -rh; }
```
This example demonstrates how to define and use these custom functions in your shell session, enhancing your productivity by providing quick access to detailed file listings and network interface statuses.

## Pitfalls
Ensure that the new aliases do not conflict with existing commands or aliases. Also, verify that the `ls` and `ifconfig` commands are available in your environment.
alias np='ping'
alias nt='traceroute'
function l() { ls -alh "$@"; }
function ni() { ifconfig "$@"; }
function fsl() { du -sh */* .[^.]* 2>/dev/null | sort -rh; }