import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import ctypes
import re
import sys
import os


# ============================================================
# Windows Power GUIDs
# ============================================================

SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"

# Processor Performance Boost Mode
PERFBOOSTMODE = "be337238-0d82-4146-a960-4f3749d470c7"


# ============================================================
# Processor Performance Boost Modes
# ============================================================

MODES = {
    0: "Disabled",
    1: "Enabled",
    2: "Aggressive",
    3: "Efficient Aggressive",
    4: "Efficient Enabled",
}

MODE_DESCRIPTIONS = {
    0: "Completely disables processor Boost/Turbo.",
    1: "Standard Boost operation.",
    2: "More aggressively increases processor frequency.",
    3: "Aggressive Boost with a greater focus on efficiency.",
    4: "Boost with a focus on power efficiency.",
}


# ============================================================
# Administrator Privileges
# ============================================================

def is_admin():
    """Check whether the application is running as administrator."""
    try:
        return bool(
            ctypes.windll.shell32.IsUserAnAdmin()
        )
    except Exception:
        return False


def restart_as_admin():
    """
    Restart the current application with administrator privileges.
    Works with both .py files and PyInstaller executables.
    """

    try:
        if is_admin():
            messagebox.showinfo(
                "Administrator",
                "The application is already running "
                "with administrator privileges."
            )
            return

        # ----------------------------------------------------
        # PyInstaller executable
        # ----------------------------------------------------

        if getattr(sys, "frozen", False):

            executable = sys.executable

            arguments = " ".join(
                f'"{arg}"'
                for arg in sys.argv[1:]
            )

        # ----------------------------------------------------
        # Normal Python script
        # ----------------------------------------------------

        else:

            executable = sys.executable

            script_path = os.path.abspath(
                sys.argv[0]
            )

            arguments = " ".join(
                [f'"{script_path}"'] +
                [
                    f'"{arg}"'
                    for arg in sys.argv[1:]
                ]
            )

        # ----------------------------------------------------
        # Request UAC elevation
        # ----------------------------------------------------

        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            arguments,
            None,
            1
        )

        if result <= 32:
            raise RuntimeError(
                f"Windows failed to start the elevated process "
                f"(error code: {result})."
            )

        # Close the non-elevated instance
        sys.exit(0)

    except Exception as e:

        messagebox.showerror(
            "Administrator Error",
            "Failed to restart the application "
            "as administrator.\n\n"
            f"{e}"
        )


# ============================================================
# powercfg
# ============================================================

def run_powercfg(args):

    try:

        result = subprocess.run(
            ["powercfg"] + args,
            capture_output=True,
            text=True,
            encoding="cp866",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        if result.returncode != 0:

            error = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"Exit code: {result.returncode}"
            )

            raise RuntimeError(error)

        return result.stdout

    except FileNotFoundError:

        raise RuntimeError(
            "powercfg.exe was not found."
        )


# ============================================================
# Get Power Schemes
# ============================================================

def get_power_schemes():

    output = run_powercfg(
        ["/list"]
    )

    schemes = []

    guid_pattern = re.compile(
        r"([0-9a-fA-F]{8}-"
        r"[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{12})"
    )

    for line in output.splitlines():

        match = guid_pattern.search(line)

        if not match:
            continue

        guid = match.group(1)

        # Text after the GUID normally contains
        # the power scheme name.
        rest = line[match.end():].strip()

        active = "*" in rest

        rest = rest.replace(
            "*",
            ""
        ).strip()

        if (
            rest.startswith("(")
            and rest.endswith(")")
        ):
            name = rest[1:-1].strip()
        else:
            name = rest.strip()

        if not name:
            name = guid

        schemes.append({
            "guid": guid,
            "name": name,
            "active": active
        })

    if not schemes:

        raise RuntimeError(
            "No power schemes were found.\n\n"
            "powercfg /list output:\n\n"
            + output
        )

    return schemes


# ============================================================
# Read Boost Mode
# ============================================================

def get_boost_mode(guid):

    output = run_powercfg([
        "/query",
        guid,
        SUB_PROCESSOR,
        PERFBOOSTMODE
    ])

    ac_value = None
    dc_value = None

    for line in output.splitlines():

        line_lower = line.lower()

        if "current ac power setting index" in line_lower:

            match = re.search(
                r"0x([0-9a-fA-F]+)",
                line
            )

            if match:

                ac_value = int(
                    match.group(1),
                    16
                )

        elif "current dc power setting index" in line_lower:

            match = re.search(
                r"0x([0-9a-fA-F]+)",
                line
            )

            if match:

                dc_value = int(
                    match.group(1),
                    16
                )

    return ac_value, dc_value


# ============================================================
# Set Boost Mode
# ============================================================

def set_boost_mode(
    guid,
    mode,
    target
):
    """
    target:
        AC   = AC power only
        DC   = battery only
        BOTH = AC and battery
    """

    if target in (
        "AC",
        "BOTH"
    ):

        run_powercfg([
            "/setacvalueindex",
            guid,
            SUB_PROCESSOR,
            PERFBOOSTMODE,
            str(mode)
        ])

    if target in (
        "DC",
        "BOTH"
    ):

        run_powercfg([
            "/setdcvalueindex",
            guid,
            SUB_PROCESSOR,
            PERFBOOSTMODE,
            str(mode)
        ])

    # Apply the selected power scheme.
    run_powercfg([
        "/setactive",
        guid
    ])


# ============================================================
# Main GUI
# ============================================================

class BoostController:

    def __init__(
        self,
        root
    ):

        self.root = root

        self.root.title(
            "CPU Boost Controller"
        )

        self.root.geometry(
            "680x610"
        )

        self.root.resizable(
            False,
            False
        )

        self.schemes = []

        self.target_var = tk.StringVar(
            value="BOTH"
        )

        self.build_ui()

        self.load_schemes()


    # ========================================================
    # Build Interface
    # ========================================================

    def build_ui(self):

        main = ttk.Frame(
            self.root,
            padding=20
        )

        main.pack(
            fill="both",
            expand=True
        )


        # ----------------------------------------------------
        # Header
        # ----------------------------------------------------

        ttk.Label(
            main,
            text="CPU Boost Controller",
            font=(
                "Segoe UI",
                18,
                "bold"
            )
        ).pack(
            anchor="w"
        )


        ttk.Label(
            main,
            text="Processor Performance Boost Mode",
            font=(
                "Segoe UI",
                10
            )
        ).pack(
            anchor="w",
            pady=(0, 20)
        )


        # ----------------------------------------------------
        # Power Scheme
        # ----------------------------------------------------

        ttk.Label(
            main,
            text="Power Scheme:",
            font=(
                "Segoe UI",
                11,
                "bold"
            )
        ).pack(
            anchor="w"
        )


        self.scheme_combo = ttk.Combobox(
            main,
            state="readonly",
            width=75
        )

        self.scheme_combo.pack(
            fill="x",
            pady=8
        )

        self.scheme_combo.bind(
            "<<ComboboxSelected>>",
            self.scheme_changed
        )


        self.scheme_info = ttk.Label(
            main,
            text=""
        )

        self.scheme_info.pack(
            anchor="w",
            pady=(0, 15)
        )


        # ----------------------------------------------------
        # Current Settings
        # ----------------------------------------------------

        self.status_label = ttk.Label(
            main,
            text="Loading current settings...",
            font=(
                "Segoe UI",
                10
            )
        )

        self.status_label.pack(
            anchor="w",
            pady=(0, 15)
        )


        ttk.Separator(
            main
        ).pack(
            fill="x",
            pady=10
        )


        # ----------------------------------------------------
        # Boost Mode
        # ----------------------------------------------------

        ttk.Label(
            main,
            text="New Boost Mode:",
            font=(
                "Segoe UI",
                11,
                "bold"
            )
        ).pack(
            anchor="w"
        )


        self.mode_combo = ttk.Combobox(
            main,
            state="readonly",
            width=75,
            values=[
                f"{number} — {name}"
                for number, name in MODES.items()
            ]
        )

        self.mode_combo.pack(
            fill="x",
            pady=8
        )

        self.mode_combo.current(1)

        self.mode_combo.bind(
            "<<ComboboxSelected>>",
            self.mode_changed
        )


        self.description = ttk.Label(
            main,
            text="",
            wraplength=630,
            justify="left"
        )

        self.description.pack(
            anchor="w",
            pady=(0, 15)
        )


        # ----------------------------------------------------
        # Apply To
        # ----------------------------------------------------

        ttk.Label(
            main,
            text="Apply To:",
            font=(
                "Segoe UI",
                11,
                "bold"
            )
        ).pack(
            anchor="w"
        )


        target_frame = ttk.Frame(
            main
        )

        target_frame.pack(
            anchor="w",
            pady=8
        )


        ttk.Radiobutton(
            target_frame,
            text="AC Power + Battery",
            variable=self.target_var,
            value="BOTH"
        ).pack(
            side="left",
            padx=(0, 15)
        )


        ttk.Radiobutton(
            target_frame,
            text="AC Power Only",
            variable=self.target_var,
            value="AC"
        ).pack(
            side="left",
            padx=(0, 15)
        )


        ttk.Radiobutton(
            target_frame,
            text="Battery Only",
            variable=self.target_var,
            value="DC"
        ).pack(
            side="left"
        )


        # ----------------------------------------------------
        # Main Buttons
        # ----------------------------------------------------

        button_frame = ttk.Frame(
            main
        )

        button_frame.pack(
            fill="x",
            pady=20
        )


        self.apply_button = ttk.Button(
            button_frame,
            text="Apply",
            command=self.apply
        )

        self.apply_button.pack(
            side="left",
            padx=(0, 10)
        )


        self.refresh_button = ttk.Button(
            button_frame,
            text="Refresh",
            command=self.load_schemes
        )

        self.refresh_button.pack(
            side="left"
        )


        # ----------------------------------------------------
        # Administrator Section
        # ----------------------------------------------------

        ttk.Separator(
            main
        ).pack(
            fill="x",
            pady=(5, 12)
        )


        if is_admin():

            admin_text = (
                "✓ Running with administrator privileges"
            )

        else:

            admin_text = (
                "⚠ Administrator privileges are not enabled"
            )


        self.admin_label = ttk.Label(
            main,
            text=admin_text
        )

        self.admin_label.pack(
            anchor="w"
        )


        # IMPORTANT:
        # This button is ALWAYS visible.

        self.admin_button = ttk.Button(
            main,
            text="🔐 Restart as Administrator",
            command=self.restart_button_clicked
        )

        self.admin_button.pack(
            anchor="w",
            pady=(8, 0)
        )


        self.mode_changed()


    # ========================================================
    # Administrator Button
    # ========================================================

    def restart_button_clicked(self):

        if is_admin():

            messagebox.showinfo(
                "Administrator",
                "The application is already "
                "running as administrator."
            )

            return

        restart_as_admin()


    # ========================================================
    # Load Power Schemes
    # ========================================================

    def load_schemes(self):

        try:

            self.schemes = get_power_schemes()

            values = []

            active_index = 0

            for i, scheme in enumerate(
                self.schemes
            ):

                marker = (
                    "★ "
                    if scheme["active"]
                    else ""
                )

                values.append(
                    f"{marker}"
                    f"{scheme['name']} "
                    f"[{scheme['guid']}]"
                )

                if scheme["active"]:

                    active_index = i


            self.scheme_combo["values"] = values

            self.scheme_combo.current(
                active_index
            )

            self.scheme_changed()


        except Exception as e:

            messagebox.showerror(
                "Error",
                "Failed to get power schemes:\n\n"
                f"{e}"
            )


    # ========================================================
    # Power Scheme Changed
    # ========================================================

    def scheme_changed(
        self,
        event=None
    ):

        index = self.scheme_combo.current()

        if (
            index < 0
            or index >= len(self.schemes)
        ):
            return


        scheme = self.schemes[index]

        state = (
            "ACTIVE"
            if scheme["active"]
            else "inactive"
        )


        self.scheme_info.config(
            text=(
                f"GUID: {scheme['guid']}"
                f"    |    {state}"
            )
        )


        self.refresh_mode()


    # ========================================================
    # Refresh Current Boost Mode
    # ========================================================

    def refresh_mode(self):

        index = self.scheme_combo.current()

        if (
            index < 0
            or index >= len(self.schemes)
        ):
            return


        guid = self.schemes[index]["guid"]


        try:

            ac, dc = get_boost_mode(
                guid
            )


            ac_name = MODES.get(
                ac,
                f"Unknown ({ac})"
            )

            dc_name = MODES.get(
                dc,
                f"Unknown ({dc})"
            )


            self.status_label.config(
                text=(
                    "Current Settings:\n"
                    f"  AC Power:  "
                    f"{ac} — {ac_name}\n"
                    f"  Battery:   "
                    f"{dc} — {dc_name}"
                )
            )


            if (
                ac == dc
                and ac in MODES
            ):

                self.mode_combo.current(
                    ac
                )


            self.mode_changed()


        except Exception as e:

            self.status_label.config(
                text=(
                    "Failed to read current mode:\n"
                    f"{e}"
                )
            )


    # ========================================================
    # Mode Description
    # ========================================================

    def mode_changed(
        self,
        event=None
    ):

        index = self.mode_combo.current()

        if index < 0:
            return


        self.description.config(
            text=MODE_DESCRIPTIONS[index]
        )


    # ========================================================
    # Apply
    # ========================================================

    def apply(self):

        if not is_admin():

            messagebox.showwarning(
                "Administrator Privileges Required",
                "Changing power settings requires "
                "administrator privileges.\n\n"
                "Please click "
                "\"Restart as Administrator\" "
                "and try again."
            )

            return


        scheme_index = (
            self.scheme_combo.current()
        )

        if scheme_index < 0:
            return


        mode = self.mode_combo.current()

        if mode not in MODES:
            return


        target = self.target_var.get()

        scheme = self.schemes[
            scheme_index
        ]


        try:

            set_boost_mode(
                scheme["guid"],
                mode,
                target
            )


            target_name = {
                "BOTH": (
                    "AC power and battery"
                ),
                "AC": (
                    "AC power only"
                ),
                "DC": (
                    "battery only"
                )
            }[target]


            messagebox.showinfo(
                "Success",
                f"Power Scheme:\n"
                f"{scheme['name']}\n\n"
                f"Boost Mode:\n"
                f"{mode} — {MODES[mode]}\n\n"
                f"Applied to: "
                f"{target_name}"
            )


            self.load_schemes()


        except Exception as e:

            messagebox.showerror(
                "Error",
                "Failed to change settings:\n\n"
                f"{e}"
            )


# ============================================================
# Application Entry Point
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    try:

        ctypes.windll.shcore.SetProcessDpiAwareness(
            1
        )

    except Exception:
        pass


    app = BoostController(
        root
    )

    root.mainloop()