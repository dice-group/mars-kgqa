import time
import os
import json
from datetime import datetime

class ProcessFlowLogger:
    def __init__(self, process_name, output_dir, enable_print=True):
        """Initialize logger with process name and output directory"""
        self.process_name = process_name
        self.output_dir = output_dir
        self.process_start_time = time.time()
        self.action_stack = []
        self.processed_actions = 0
        
        self.enable_print = enable_print
        
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Set up log file path
        self.log_file_path = ProcessFlowLogger.gen_log_file_path(self.process_name, self.output_dir)
        self._fh = open(self.log_file_path, "a", buffering=1)
        
        # Write process header
        self._write_section_header("PROCESS START", self.process_name)
        self._write_line(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_separator()
        
    def gen_log_file_path(proc_name, output_dir):
        return os.path.join(output_dir, f"{proc_name}_log.txt")

    def close(self):
        """Close the log file"""
        if hasattr(self, '_fh') and not self._fh.closed:
            self._fh.close()

    def _write_line(self, text=""):
        """Write a single line to the log"""
        self._fh.write(text + "\n")
        self._fh.flush()
        if self.enable_print:
            print(text)  # Also print to console

    def _write_separator(self):
        """Write a separator line"""
        self._write_line("─" * 80)

    def _write_section_header(self, section_type, title):
        """Write a formatted section header"""
        header = f"┌─ {section_type}: {title} ────────────────────────────────────────────────────"
        self._write_line(header)
        self._write_line(f"├─ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def log_input_info(self, input_data):
        """Log process input information"""
        self._write_section_header("INPUT RECEIVED", str(input_data)[:50] + "..." if len(str(input_data)) > 50 else str(input_data))
        self._write_line(json.dumps(input_data, indent=2, ensure_ascii=False))
        self._write_separator()
        return self

    def start_action(self, action_name, input_data=None):
        """Start a new action logging session with nested support"""
        indent_level = len(self.action_stack)
        indent = "    " * indent_level  # 4 spaces per level
        
        # Add visual hierarchy indicators
        if indent_level == 0:
            prefix = "┌─"
        elif indent_level == 1:
            prefix = "├─"
        else:
            prefix = "├─"
            
        self._write_line(f"{indent}{prefix} STARTING ACTION: {action_name}")
        
        if input_data:
            # Format input with proper indentation
            indent_input = "    " * (indent_level + 1)
            input_json = json.dumps(input_data, indent=2, ensure_ascii=False)
            input_lines = input_json.split('\n')
            for line in input_lines:
                if line.strip():  # Skip empty lines
                    self._write_line(f"{indent_input}│ {line}")
        
        # Create action record
        action = {
            "name": action_name,
            "start_time": time.time(),
            "steps": [],
            "output": None,
            "indent_level": indent_level
        }
        self.action_stack.append(action)
        return self

    def add_step(self, step_description):
        """Add intermediate step to current action"""
        if not self.action_stack:
            return self

        action = self.action_stack[-1]
        # Record the step so the step count persists
        step_num = self._record_step(action, step_description)

        indent_level = action["indent_level"] + 1
        indent = "    " * indent_level
        timestamp = datetime.now().strftime('%H:%M:%S')
        prefix = "├─"

        self._write_line(f"{indent}{prefix} Step {step_num}: {step_description} [{timestamp}]")
        return self

    def _record_step(self, action, description):
        """Store a step in the action and return its sequential number."""
        step_entry = {
            "description": description,
            "timestamp": datetime.now().isoformat()
        }
        action["steps"].append(step_entry)
        return len(action["steps"])

    def set_output(self, output_data):
        """Set output for current action"""
        if self.action_stack:
            action = self.action_stack[-1]
            indent_level = action["indent_level"] + 1
            indent = "    " * indent_level
            
            # Add output header with proper alignment
            indent_output = "    " * (indent_level + 1)
            self._write_line(f"{indent}├─ OUTPUT:")
            
            # Format output with proper indentation
            output_json = json.dumps(output_data, indent=2, ensure_ascii=False)
            output_lines = output_json.split('\n')
            
            # Add output content with proper indentation
            for line in output_lines:
                if line.strip():  # Skip empty lines
                    self._write_line(f"{indent_output}│ {line}")
        return self

    def complete_action(self):
        """Complete current action logging and calculate duration"""
        if not self.action_stack:
            return self
            
        action = self.action_stack.pop()
        duration = time.time() - action["start_time"]
        indent_level = action["indent_level"]
        indent = "    " * indent_level
        
        # Determine prefix based on nesting level
        if indent_level == 0:
            prefix = "└─"
        else:
            prefix = "└─"
            
        self.processed_actions += 1
        self._write_line(f"{indent}{prefix} COMPLETED: {action['name']} (took {duration:.3f}s)")
        
        # Add separator only for top-level actions
        if indent_level == 0:
            self._write_separator()
        return self

    def write_log(self):
        """Write final summary entry with total process duration"""
        total_duration = time.time() - self.process_start_time
        self._write_section_header("PROCESS SUMMARY", "Completed Successfully")
        self._write_line(f"Total Duration: {total_duration:.3f} seconds")
        self._write_line(f"Actions Performed: {self.processed_actions}")
        self._write_line(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_line(f"Average Action Duration: {total_duration/max(1, self.processed_actions):.3f}s")
        self._write_separator()
        return self


# Example usage with nested actions
if __name__ == "__main__":
    logger = ProcessFlowLogger("data_processing", "./")
    logger.log_input_info({"source": "api", "params": {"limit": 100}})

    # Top-level action
    logger.start_action("Data Processing Pipeline", {"input_size": "1GB"})
    logger.add_step("Initializing processing environment")
    
    # Nested action 1
    logger.start_action("Data Fetch", {"source": "external_api"})
    logger.add_step("Connecting to API endpoint")
    logger.add_step("Authentication successful")
    logger.add_step("Fetching data records")
    logger.set_output({"records": 1000, "status": "success"})
    logger.complete_action()
    
    # Nested action 2
    logger.start_action("Data Transformation", {"input_records": 1000})
    logger.add_step("Applying data filters")
    logger.add_step("Running validation checks")
    logger.add_step("Converting data formats")
    logger.set_output({"processed_records": 850, "reduction": 15})
    logger.complete_action()
    
    logger.add_step("Generating final output")
    logger.set_output({"status": "completed", "records": 850})
    logger.complete_action()
    logger.write_log()