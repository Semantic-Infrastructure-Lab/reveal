package lib

import (
	"fmt"

	"github.com/spf13/cobra"
)

func main() {
	used()
}

func used() {
	fmt.Println(cobra.Use)
}

func orphan() {}
