
async () => {
    const results = [];
    const ports = [22, 80, 443, 8080, 8443, 8888, 8889, 9090, 3000, 5000, 8000, 9000, 9200, 9300];
    const ips = ['127.0.0.1', 'localhost', '0.0.0.0', '10.183.55.170', '192.168.0.1', '192.168.1.1'];

    for (const ip of ips) {
        for (const port of ports) {
            const start = performance.now();
            try {
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 500);
                await fetch(`http://${ip}:${port}`, {signal: controller.signal, mode: 'no-cors'});
                clearTimeout(timeout);
                const elapsed = performance.now() - start;
                results.push(`OPEN:${ip}:${port}:${elapsed.toFixed(0)}ms`);
            } catch (e) {
                const elapsed = performance.now() - start;
                if (elapsed > 400) {
                    results.push(`TIMEOUT:${ip}:${port}:${elapsed.toFixed(0)}ms`);
                }
            }
        }
    }
    return results.join('\n');
}
