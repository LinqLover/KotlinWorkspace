import os
import psutil
import selectors
import subprocess
from threading import Thread


KOTLINC = 'kotlinc'


class BaseScriptRunner(Thread):
    """
    Runs a script in a separate thread and sends output to the output queue.

    The output queue will receive tuples of the form (stream, chunk) like this:
        ('stdout', 'Hello, world!')
        ('stderr', 'Error: foo is not defined')
        ('exit', 1)
    """
    def __init__(self, script_name, output_queue):
        super().__init__()
        self.script_name = script_name
        self.output_queue = output_queue
        self.process = None

    def reset(self):
        try:
            os.remove(self.script_name)
        except FileNotFoundError:
            pass

    def stop(self):
        # We need to kill the process and all its children because kotlinc
        # spawns a java process but doesn't kill it when it receives SIGTERM
        # autc.
        try:
            parent = psutil.Process(self.process.pid)
            try:
                children = parent.children()
                for child in children:
                    try:
                        child.kill()
                    except:
                        pass
            except:
                pass
            try:
                parent.kill()
            except:
                pass
        except:
            pass

    def _run_script(self):
        try:
            self.process = self._create_process()
        except FileNotFoundError:
            self.output_queue.put(('stderr', f"{KOTLINC} not found. Please make sure it is in your PATH."))
            return 127

        with self.process:
            selector = selectors.DefaultSelector()
            selector.register(self.process.stdout, selectors.EVENT_READ)
            selector.register(self.process.stderr, selectors.EVENT_READ)
            exited = False
            while not exited:
                for key, val1 in selector.select(timeout=0.1):
                    chunk = key.fileobj.read1().decode()
                    if not chunk:
                        exited = True
                        break
                    if key.fileobj is self.process.stdout:
                        self.output_queue.put(('stdout', chunk))
                    else:
                        self.output_queue.put(('stderr', chunk))

        exit_code = self.process.wait()
        self.process = None
        return exit_code

    def _create_process(self):
        raise NotImplementedError


class ScriptRunner(BaseScriptRunner):
    """
    A simple script runner that lives and dies with the script.
    """
    def __init__(self, script_name, output_queue, script):
        super().__init__(script_name, output_queue)
        self.script = script

    def run(self):
        with open(self.script_name, 'w') as f:
            f.write(self.script)

        exit_code = self._run_script()
        self.output_queue.put(('exit', exit_code))

        self.reset()

    def _create_process(self):
        return subprocess.Popen(
            [KOTLINC, '-script', self.script_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )


class HotScriptRunner(BaseScriptRunner):
    """
    A more efficient script runner that lives for the duration of the program.

    This version already starts kotlinc before it receives the script. To do
    so, we pass a file descriptor to the compiler and later write the script
    to it. Because kotlinc only supports reading from .kts files, we create a
    symlink to the file descriptor.
    """
    def __init__(self, script_name, output_queue):
        super().__init__(script_name, output_queue)

        self.refresh()

    def refresh(self):
        self.reset()

        self.fd_in, self.fd_out = os.pipe()
        os.symlink(f'/proc/self/fd/{self.fd_in}', self.script_name)

    def reset(self):
        try:
            os.close(self.fd_in)
            self.fd_in = None
        except:
            pass
        try:
            os.close(self.fd_out)
            self.fd_out = None
        except:
            pass

        self.stop()

        super().reset()

    def run(self):
        self.is_running = True
        while True:
            exit_code = self._run_script()
            self.output_queue.put(('exit', exit_code))
            if not self.is_running:
                break
            self.refresh()

    def _create_process(self):
        return subprocess.Popen(
            [KOTLINC, '-script', self.script_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=[self.fd_in]
        )

    def write(self, script):
        """
        Pass the new script to the compiler.
        """
        os.write(self.fd_out, script.encode())
        os.close(self.fd_out)

    def end(self):
        """
        Stop the thread and kill the compiler.
        """
        self.is_running = False
        self.reset()
