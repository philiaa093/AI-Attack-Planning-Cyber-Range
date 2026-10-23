"""Fixed ZAP API workflow inside the isolated scanner network namespace."""
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.error
import urllib.request


def main():
    job = json.load(sys.stdin)
    # No target request uses this client: it addresses only the local ZAP API.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(component, kind, operation, **params):
        url = f"http://127.0.0.1:8090/JSON/{component}/{kind}/{operation}/?"
        try:
            with opener.open(url + urllib.parse.urlencode(params), timeout=10) as response:
                value = json.load(response)
        except urllib.error.HTTPError as exc:
            value = json.load(exc)
            raise RuntimeError("ZAP_API_" + str(value.get("code", exc.code))) from None
        if isinstance(value, dict) and "code" in value:
            raise RuntimeError("ZAP_API_" + str(value["code"]))
        return value

    args = ["/zap/zap.sh", "-daemon", "-host", "127.0.0.1", "-port", "8090", "-dir", "/tmp/zap",
            "-config", "api.disablekey=true", "-config", "autoupdate.checkOnStart=false",
            "-config", "autoupdate.downloadNewRelease=false", "-config", "autoupdate.installAddonUpdates=false"]
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError("ZAP_START_FAILED")
            try:
                version = api("core", "view", "version")["version"]
                break
            except (OSError, ValueError):
                time.sleep(0.5)
        else:
            raise RuntimeError("ZAP_START_TIMEOUT")
        api("network", "action", "setHttpProxy", host="127.0.0.1", port=8081)
        api("network", "action", "setHttpProxyEnabled", enabled="true")
        api("ascan", "action", "disableAllScanners")
        if job["active"]:
            api("ascan", "action", "enableScanners", ids="40012,40018")
            api("ascan", "action", "setOptionThreadPerHost", Integer=1)
        for url in job["urls"]:
            api("core", "action", "accessUrl", url=url, followRedirects="false")
        for url in job["urls"]:
            if job["active"]:
                # ZAP inserts accessed messages into its site tree asynchronously.
                for _ in range(50):
                    if url in api("core", "view", "urls")["urls"]:
                        break
                    time.sleep(0.1)
                scan = api("ascan", "action", "scan", url=url, method="GET", postData="",
                           recurse="false", inScopeOnly="false")["scan"]
                while int(api("ascan", "view", "status", scanId=scan)["status"]) < 100:
                    time.sleep(0.2)
        while int(api("pscan", "view", "recordsToScan")["recordsToScan"]):
            time.sleep(0.2)
        with opener.open("http://127.0.0.1:8090/OTHER/core/other/jsonreport/", timeout=10) as response:
            report = json.load(response)
        print(json.dumps({"version": version, "report": report}))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
