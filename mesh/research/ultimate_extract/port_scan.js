
async () => {
    const results = [];
    for (const port of [8888, 8443, 5900, 6901, 22, 80, 443, 9222, 9223, 3000, 8080, 5000, 8000]) {
        try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 2000);
            await fetch(`http://localhost:${port}`, {signal: controller.signal, mode: 'no-cors'});
            clearTimeout(timeout);
            results.push(`OPEN:${port}`);
        } catch (e) {
            if (e.name === 'AbortError') {
                results.push(`TIMEOUT:${port}`);
            } else {
                results.push(`CLOSED:${port}`);
            }
        }
    }
    return results.join(', ');
}
