# Provide different functions to log specific steps during the process

# Constructor to initiate the log with process name and directory to store output

# Function to log process input info

# Function to log action, its input, intermediate steps and its output

# Log time required for an action and allow action logger object to be passed around to keep on adding logs until a complete function is called

# Function to write the output log and compute the full run-time of the process
import time
import os
import json
import atexit

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

    def log_input_info(self, input_data):
        """Log process input information"""
        entry = {
            "type": "input",
            "data": input_data,
            "timestamp": time.time()
        }
        self.log_entries.append(entry)
        self._write_entry(entry)
        return self

    def start_action(self, action_name, input_data):
        """Start a new action logging session"""
        self.current_action = {
            "name": action_name,
            "input": input_data,
            "start_time": time.time(),
            "steps": [],
            "output": None
        }
        return self

    def add_step(self, step_description):
        """Add intermediate step to current action"""
        if self.current_action:
            self.current_action["steps"].append({
                "description": step_description,
                "timestamp": time.time()
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
            self.current_action["duration"] = time.time() - self.current_action["start_time"]
            self.current_action["end_time"] = time.time()
            action_entry = {
                "type": "action",
                "action": self.current_action
            }
            self.log_entries.append(action_entry)
            self._write_entry(action_entry)
            self.current_action = None
        return self

    def write_log(self):
        """Write final summary entry with total process duration"""
        summary_entry = {
            "type": "process_summary",
            "end_time": time.time(),
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