// Independent source import facts from Go's standard parser, never Reveal.
package main

import (
	"encoding/json"
	"fmt"
	"go/parser"
	"go/token"
	"os"
	"strconv"
)

func main() {
	var files []string
	if err := json.NewDecoder(os.Stdin).Decode(&files); err != nil {
		fail(err)
	}
	imports := make(map[string][]string)
	for _, name := range files {
		tree, err := parser.ParseFile(token.NewFileSet(), name, nil, parser.ImportsOnly)
		if err != nil {
			fail(err)
		}
		imports[name] = []string{}
		for _, spec := range tree.Imports {
			path, err := strconv.Unquote(spec.Path.Value)
			if err != nil {
				fail(err)
			}
			imports[name] = append(imports[name], path)
		}
	}
	if err := json.NewEncoder(os.Stdout).Encode(imports); err != nil {
		fail(err)
	}
}

func fail(err error) { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
