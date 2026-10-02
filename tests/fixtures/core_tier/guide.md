---
title: Order Service Guide
status: current
---

# Order Service Guide

The order service validates, logs and batches orders.
This intro sits above the first second-level heading.

## Setup

Install the service and point it at a log directory.

### Requirements

- Python 3.10 or newer
- A writable log directory

### Configuration

Set `ORDER_LOG` to the log path.

```bash
# not a heading: a shell comment inside a fence
export ORDER_LOG=/var/log/orders.log
```

## Usage

Call `process_order(order)` for each order.

### Batching

`Batch.run(items)` totals a list and caches each item.

## Release 1.1

### Fixed

- Empty orders no longer raise.

## Release 1.0

### Fixed

- First release.

## See [the API](api.md) &amp; notes ##

Cross-references live here.

## Known gaps

## 2026

Plans for the year.
