export function configuredName(fallback: string): string {
    return process.env.REVEAL_PARSE_GATE_NAME || fallback;
}
