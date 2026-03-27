---
title: Custom Shell Function for Quick File Listing and Network Interface Status Monitoring
tags: shell, ls, ifconfig, productivity
complexity: low
summary: Adds custom shell functions to quickly list files with detailed information and monitor network interfaces.
---
## When to use
Use this skill when you frequently need to check file details in your directory and prefer a quick command to do so. Additionally, it's useful when needing to quickly assess the status of network interfaces.

## Approach
Create two custom shell functions: `l` that uses the `ls` command with `-alh` options for detailed file listings, and `ni` that uses the `ifconfig` command for a quick overview of network interface statuses. These can be added directly into your user profile preferences.

## Example
```shell
function l() { ls -alh "$@"; }
function ni() { ifconfig "$@"; }
```
This example demonstrates how to define and use both custom functions in your shell session.

## Pitfalls
Ensure that the new aliases do not conflict with existing commands or aliases. Also, verify that the `ls` and `ifconfig` commands are available in your environment.
alias np='ping'
alias nt='traceroute'
function l() { ls -alh "$@"; }
function ni() { ifconfig "$@"; }