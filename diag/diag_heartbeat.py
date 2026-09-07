import time
for i in range(30):
    print(f"beat {i} {time.strftime('%H:%M:%S')}", flush=True)
    time.sleep(10)
print("HEARTBEAT-DONE", flush=True)
