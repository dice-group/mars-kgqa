import time
import os
import json
import atexit
from datetime import datetime

class ProcessFlowLogger:
    def __init__(self, process_name, output_dir):
        """Initialize logger with process name and output directory"""
        self.process_name = process_name
        self.output_dir = output_dir
        self.log_entries = []                     # kept for backward compatibility
        self.process_start_time = time.time()
        self.current_action = None

        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)

        # ---- open file once (JSON‑Lines) ----
        self.log_file_path = os.path.join(
            self.output_dir, f"{self.process_name}_log.jsonl")
        # open in append mode so we can reuse the same handle after a crash/restart
        self._fh = open(self.log_file_path, "a", buffering=1)  # line‑buffered
        atexit.register(self.close)  # ensure file gets closed on interpreter exit

        # Write a header entry for the process start
        self._write_entry({
            "type": "process_start",
            "process_name": self.process_name,
            "start_time": self.process_start_time
        })

    def close(self):
        """Flush and close the underlying file handle."""
        try:
            self._fh.flush()
            self._fh.close()
        except Exception:
            pass  # ignore errors during interpreter shutdown

    def _write_entry(self, entry: dict):
        """Append a single log entry to the JSON‑Lines file using the open handle."""
        json.dump(entry, self._fh)
        self._fh.write("\n")
        self._fh.flush()          # optional – guarantees entry is on disk immediately
        print(json.dumps(entry)) # printing to standard io as well

    def log_input_info(self, input_data):
        """Log process input information"""
        entry = {
            "type": "input",
            "data": input_data,
            "timestamp": datetime.now().isoformat()  
        }
        self.log_entries.append(entry)
        self._write_entry(entry)
        return self

    def start_action(self, action_name, input_data):
        """Start a new action logging session"""
        now = time.time()
        self.current_action = {
            "name": action_name,
            "input": input_data,
            "start_time": datetime.fromtimestamp(now).isoformat(),  # readable
            "_start_ts": now,                                         # raw for duration
            "steps": [],
            "output": None
        }
        return self

    def add_step(self, step_description):
        """Add intermediate step to current action"""
        if self.current_action:
            self.current_action["steps"].append({
                "description": step_description,
                "timestamp": datetime.now().isoformat()  
            })
        return self

    def set_output(self, output_data):
        """Set output for current action"""
        if self.current_action:
            self.current_action["output"] = output_data
        return self

    def complete_action(self):
        """Complete current action logging and calculate duration"""
        if self.current_action:
            end_ts = time.time()
            self.current_action["duration"] = end_ts - self.current_action["_start_ts"]
            self.current_action["end_time"] = datetime.fromtimestamp(end_ts).isoformat()
            # remove internal raw timestamp before writing (optional)
            action_entry = {
                "type": "action",
                "action": {k: v for k, v in self.current_action.items() if k != "_start_ts"}
            }
            self.log_entries.append(action_entry)
            self._write_entry(action_entry)
            self.current_action = None
        return self

    def write_log(self):
        """Write final summary entry with total process duration"""
        summary_entry = {
            "type": "process_summary",
            "end_time": datetime.now().isoformat(),  
            "total_duration": time.time() - self.process_start_time
        }
        self._write_entry(summary_entry)
        return self


# Example usage
if __name__ == "__main__":
    proc_logger = ProcessFlowLogger("data_processing", "./logs")
    proc_logger.log_input_info({"source": "api", "params": {"limit": 100}})

    # Process action 1
    action1 = proc_logger.start_action("data_fetch", {"url": "https://api.example.com"})
    action1.add_step("Connecting to API")
    action1.add_step("Parsing response")
    action1.set_output({"records": 100, "status": "success"})
    action1.complete_action()

    # Process action 2
    action2 = proc_logger.start_action("data_transform", {"input": "previous_output"})
    action2.add_step("Applying filters")
    action2.set_output({"processed_records": 85})
    action2.complete_action()

    proc_logger.write_log()