"""`network` rule rows for socket clients (BACK-1334 slice e; the BACK-1319 leftovers).

Import-shaped rows (`surface_rules_imports.py`) cannot see a client that lives in the standard
library: Go's `net`, Rust's `std::net`, Ruby's `TCPSocket`, .NET's `System.Net.Sockets`,
Foundation's `URLSession`. A program that dials a TCP socket therefore reported `network: 0`.
These rows match the call or constructor that opens the connection instead.

Client-side only: `net.Listen` / `TcpListener::bind` are servers (inbound, the `http`/`cli`
categories' business). `URLSession` is matched on `URLSession.shared.<task>` and on the
`URLSession(...)` constructor; a task started on a stored session variable
(`session.dataTask(...)`) needs type binding and is not seen. Not covered here: TypeScript
`net.connect` (needs binding resolution, BACK-1335) and Java/Kotlin (the `java.net` import
rows already flag them).
"""

from .surface_rules import Call, ImportedFrom, New, Rule

_C = 'network'

RULES = (
    # ── Go ──────────────────────────────────────────────────────────────────
    # `net.Dial` is egress only when the file imports `net`: another package or a local
    # variable named `net` is a lookalike.
    Rule(_C, 'go',
         Call(receiver='net',
              name=('Dial', 'DialTimeout', 'DialTCP', 'DialUDP', 'DialUnix', 'DialIP')),
         '{path}',
         requires=ImportedFrom('net'),
         example='package main\nimport "net"\nfunc f() { net.Dial("tcp", "a:1") }\n',
         counter_examples=(
             'package main\nfunc f(c cfg) { c.Dial("tcp", "a:1") }\n',
             'package main\nfunc f() { net.Dial("tcp", "a:1") }\n',      # no `net` import
         ),
         entry_type='call'),

    # ── Rust ────────────────────────────────────────────────────────────────
    # `std::net::TcpStream` and `tokio::net::TcpStream` both end in `net::TcpStream`.
    Rule(_C, 'rust',
         Call(receiver_endswith='net::TcpStream', name=('connect', 'connect_timeout')),
         'TcpStream::{name}',
         example='fn f() { let _ = std::net::TcpStream::connect("a:1"); }\n',
         entry_type='call'),
    Rule(_C, 'rust', Call(receiver='TcpStream', name=('connect', 'connect_timeout')),
         'TcpStream::{name}',
         requires=ImportedFrom('net::TcpStream'),
         example='use std::net::{TcpStream, UdpSocket};\nfn f() { let _ = TcpStream::connect("a:1"); }\n',
         counter_examples=(
             'fn f() { let _ = TcpStream::connect("a:1"); }\n',                    # no import
             'use mine::TcpStream;\nfn f() { let _ = TcpStream::connect("a:1"); }\n',
         ),
         entry_type='call'),

    # ── Ruby ────────────────────────────────────────────────────────────────
    Rule(_C, 'ruby', Call(receiver='TCPSocket', name=('new', 'open')), '{receiver}.{name}',
         example="require 'socket'\ns = TCPSocket.new('a', 1)\n",
         counter_examples=("x = Foo.new('a', 1)\ny = obj.TCPSocket.new('a', 1)\n",),
         entry_type='call'),
    Rule(_C, 'ruby', Call(receiver='Socket', name='tcp'), '{receiver}.{name}',
         example="require 'socket'\nSocket.tcp('a', 1) { |s| s.puts 1 }\n",
         entry_type='call'),

    # ── C# ──────────────────────────────────────────────────────────────────
    Rule(_C, 'csharp', New(type=('TcpClient', 'UdpClient', 'ClientWebSocket')), 'new {type}()',
         example='using System.Net.Sockets;\nclass A { void F() { var c = new TcpClient("a", 1); } }\n',
         counter_examples=('class A { void F() { var c = new TcpClientX("a", 1); } }\n',),
         entry_type='call'),

    # ── Swift ───────────────────────────────────────────────────────────────
    Rule(_C, 'swift',
         Call(receiver='URLSession.shared',
              name=('dataTask', 'downloadTask', 'uploadTask', 'data', 'download', 'upload',
                    'webSocketTask')),
         '{path}',
         example=('import Foundation\nfunc f() {\n'
                  '  URLSession.shared.dataTask(with: url) { _, _, _ in }.resume()\n}\n'),
         counter_examples=('func f(c Conn) {\n  c.shared.dataTask(with: url)\n}\n',),
         entry_type='call'),
    Rule(_C, 'swift', Call(receiver='', name='URLSession'), 'URLSession()',
         example='import Foundation\nfunc f() {\n  let s = URLSession(configuration: .default)\n}\n',
         entry_type='call'),
)
