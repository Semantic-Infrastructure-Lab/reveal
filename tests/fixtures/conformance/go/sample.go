// Conformance fixture (BACK-422 Tier 1) — Go
package sample

import (
	"errors"
	"fmt"
	"os"
	"strconv" // unused on purpose -- must still be flagged by imports://
	"strings"
)

func validate(order string) (string, error) {
	if order == "" {
		return "", errors.New("empty order")
	}
	return order, nil
}

func processOrder(order string) (string, error) {
	result, err := validate(order)
	if err != nil {
		return "", err
	}
	f, err := os.OpenFile("/tmp/orders.log", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return "", err
	}
	defer f.Close()
	fmt.Fprintf(f, "%s", result)
	result = strings.ToUpper(result)
	return result, nil
}

func Run(order string) (string, error) {
	return processOrder(order)
}
