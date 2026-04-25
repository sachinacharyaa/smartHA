import json
import os
import tkinter as tk
import threading
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk


DATA_FILE = Path(__file__).with_name("health_records.json")
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
SYMPTOM_OPTIONS = [
    "Fever",
    "Cough",
    "Shortness of breath",
    "Chest pain",
    "Headache",
    "Migraine",
    "Skin rash",
    "Itching",
    "Stomach pain",
    "Vomiting",
    "Acidity",
    "Body weakness",
]
SERPER_API_KEY = "86f1eeca7c50e8786a426693edd336dac0ff2e0c"


@dataclass
class UserLogin:
    username: str
    logged_in_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class HealthResult:
    bmi: float
    bmi_status: str
    fever_status: str
    recommended_doctor: str
    advice: str
    ai_suggestion: str


@dataclass
class HealthRecord:
    created_at: str
    user: UserLogin
    weight_kg: float
    height_cm: float
    body_temp_c: float
    blood_group: str
    hereditary_condition: str
    symptoms: list
    result: HealthResult


class HealthStorage:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.records = []
        self._load()

    def _load(self):
        if not self.file_path.exists():
            self.records = []
            return
        try:
            self.records = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.records = []

    def add(self, record: HealthRecord):
        self.records.append(asdict(record))
        self._save()

    def _save(self):
        self.file_path.write_text(json.dumps(self.records, indent=2), encoding="utf-8")


def safe_float(value: str, field_name: str) -> float:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} is required.")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return parsed


def classify_bmi(bmi: float):
    if bmi < 18.5:
        return "Underweight", "Increase nutrition and discuss with a physician if persistent."
    if bmi < 25:
        return "Normal Weight", "Maintain a balanced diet and regular exercise."
    if bmi < 30:
        return "Overweight", "Improve activity and food habits; monitor weight regularly."
    return "Obese", "Consult a doctor for a structured weight management plan."


def check_fever(temp_c: float):
    if temp_c >= 39.0:
        return "High Fever"
    if temp_c >= 37.5:
        return "Mild Fever"
    return "No Fever"


def doctor_from_symptoms(symptoms: list, fever_status: str, bmi_status: str):
    text = " ".join(symptoms).lower()
    if any(word in text for word in ["chest pain", "heart", "palpitation"]):
        return "Cardiologist"
    if any(word in text for word in ["skin", "rash", "itch"]):
        return "Dermatologist"
    if any(word in text for word in ["headache", "seizure", "migraine", "nerve"]):
        return "Neurologist"
    if any(word in text for word in ["stomach", "vomit", "acid", "digestion"]):
        return "Gastroenterologist"
    if any(word in text for word in ["cough", "breath", "asthma", "lung"]):
        return "Pulmonologist"
    if fever_status != "No Fever":
        return "General Physician"
    if bmi_status in {"Overweight", "Obese"}:
        return "Nutritionist / General Physician"
    return "General Physician"


def local_advice(bmi_status: str, fever_status: str, symptoms: list, hereditary_condition: str):
    advice_parts = [f"BMI status: {bmi_status}.", f"Fever check: {fever_status}."]
    if symptoms:
        advice_parts.append(f"Symptoms noted: {', '.join(symptoms)}.")
    if hereditary_condition == "Yes":
        advice_parts.append("Hereditary risk mentioned. Please share family history with your doctor.")
    advice_parts.append("This system provides guidance only, not a medical diagnosis.")
    return " ".join(advice_parts)


def doctor_style_response(
    *,
    bmi_status: str,
    fever_status: str,
    temp_c: float,
    symptoms: list,
    hereditary_condition: str,
    recommended_doctor: str,
    web_context: str,
):
    symptoms_text = ", ".join(symptoms) if symptoms else "no major symptoms selected"
    urgent = temp_c >= 39.0 or any(s in symptoms for s in ["Chest pain", "Shortness of breath"])
    moderate = fever_status == "Mild Fever" or any(s in symptoms for s in ["Cough", "Vomiting", "Stomach pain"])

    if urgent:
        priority = "HIGH PRIORITY"
        action_window = "Seek same-day in-person care or emergency support."
    elif moderate:
        priority = "MODERATE PRIORITY"
        action_window = "Book a doctor consultation within 24 hours."
    else:
        priority = "ROUTINE PRIORITY"
        action_window = "Start home care and monitor closely for 24-48 hours."

    home_steps = [
        "- Hydrate well and take adequate rest.",
        "- Monitor temperature every 6-8 hours and note symptom changes.",
        "- Eat light, easy-to-digest meals until symptoms settle.",
    ]
    if fever_status != "No Fever":
        home_steps.append("- For fever discomfort, discuss safe antipyretic use with your pharmacist/doctor.")
    if hereditary_condition == "Yes":
        home_steps.append("- Because of hereditary risk, share family history during consultation.")

    red_flags = [
        "- Breathing difficulty, chest pain, confusion, persistent vomiting.",
        "- Fever >= 103 F (39.4 C), seizure, severe dehydration, or worsening weakness.",
        "- Any rapid worsening despite initial home care.",
    ]

    web_line = ""
    if web_context.strip():
        web_line = f"\nSupporting web check: {web_context}\n"

    return (
        "CLINICAL GUIDANCE (PRELIMINARY)\n"
        f"Priority: {priority}\n"
        f"Current findings: Temperature {temp_c:.1f} C ({fever_status}), BMI category {bmi_status}, symptoms: {symptoms_text}.\n"
        f"Most suitable doctor: {recommended_doctor}\n\n"
        "What to do now:\n"
        f"{action_window}\n"
        + "\n".join(home_steps)
        + "\n\n"
        "Go to urgent care immediately if:\n"
        + "\n".join(red_flags)
        + "\n"
        + web_line
        + "\nNote: This is supportive triage guidance, not a confirmed diagnosis."
    )


def serper_suggestion(payload_text: str):
    api_key = (SERPER_API_KEY or "").strip() or os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        return "Serper API key is missing in backend configuration."

    # Serper search works best with concise query text.
    query = "health symptoms guidance " + " ".join(payload_text.split())[:320]
    request_payload = {"q": query}
    try:
        req = urllib.request.Request(
            url="https://google.serper.dev/search",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-API-KEY": api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=40) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw)

        snippets = []
        answer_box = parsed.get("answerBox") or {}
        if answer_box.get("answer"):
            snippets.append(str(answer_box["answer"]).strip())
        if answer_box.get("snippet"):
            snippets.append(str(answer_box["snippet"]).strip())

        for item in (parsed.get("organic") or [])[:3]:
            title = (item.get("title") or "Untitled").strip()
            snippet = (item.get("snippet") or "").strip()
            if snippet:
                snippets.append(f"{title}: {snippet}")

        if not snippets:
            return "Serper returned no useful search results for these symptoms."
        # Keep only short context for doctor-style synthesis.
        compact = " | ".join(snippets[:2])
        return compact[:420]
    except urllib.error.HTTPError as exc:
        try:
            details = exc.read().decode("utf-8")
        except Exception:
            details = str(exc)
        if exc.code in {401, 403}:
            return "Serper authentication failed. Please verify your API key."
        if exc.code == 429:
            return "Serper rate limit reached. Please check your plan and usage."
        return f"Serper API error ({exc.code}): {details}"
    except urllib.error.URLError as exc:
        return f"Network error while contacting Serper: {exc}"
    except Exception as exc:
        return f"Serper call failed: {exc}"


def build_app():
    storage = HealthStorage(DATA_FILE)
    root = tk.Tk()
    root.title("Health Assistant (BMI + Fever + Symptoms)")
    root.geometry("920x720")
    root.minsize(860, 640)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TLabel", font=("Segoe UI", 10))
    style.configure("Header.TLabel", font=("Segoe UI Semibold", 20))
    style.configure("Section.TLabel", font=("Segoe UI Semibold", 11))
    style.configure("TButton", padding=6)

    page_container = ttk.Frame(root, padding=16)
    page_container.pack(fill="both", expand=True)
    page_container.rowconfigure(0, weight=1)
    page_container.columnconfigure(0, weight=1)

    current_user = {"session": None}
    active_job = {"thread": None}

    login_page = ttk.Frame(page_container)
    login_page.grid(row=0, column=0, sticky="nsew")
    login_page.columnconfigure(0, weight=1)
    login_page.rowconfigure(1, weight=1)

    form_page = ttk.Frame(page_container)
    form_page.grid(row=0, column=0, sticky="nsew")
    form_page.columnconfigure(0, weight=1)
    form_page.rowconfigure(1, weight=1)

    def show_page(page: ttk.Frame):
        page.tkraise()

    login_card = ttk.LabelFrame(login_page, text="Secure Login", padding=18)
    login_card.grid(row=1, column=0, sticky="n", pady=(30, 0), ipadx=20, ipady=8)
    login_card.columnconfigure(1, weight=1)

    username_var = tk.StringVar()
    login_status_var = tk.StringVar(value="Please login to continue")
    user_status_var = tk.StringVar(value="Not logged in")

    ttk.Label(login_page, text="Health Consultation Assistant", style="Header.TLabel").grid(
        row=0, column=0, sticky="w", pady=(0, 8)
    )
    ttk.Label(login_page, text="Professional health intake workflow").grid(row=0, column=0, sticky="e", pady=(0, 8))

    ttk.Label(login_card, text="Username").grid(row=0, column=0, sticky="w", padx=8, pady=8)
    ttk.Entry(login_card, textvariable=username_var, width=34).grid(row=0, column=1, sticky="ew", padx=8, pady=8)
    ttk.Label(login_card, textvariable=login_status_var).grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))

    def do_login():
        username = username_var.get().strip()
        if not username:
            messagebox.showerror("Login Error", "Username is required.")
            return
        current_user["session"] = UserLogin(username=username)
        user_status_var.set(f"Logged in as {username}")
        login_status_var.set("Login successful. Opening patient intake...")
        show_page(form_page)

    ttk.Button(login_card, text="Login", command=do_login).grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=8)

    top_frame = ttk.Frame(form_page)
    top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    top_frame.columnconfigure(0, weight=1)
    top_frame.columnconfigure(1, weight=1)
    ttk.Label(top_frame, text="Patient Intake Form", style="Header.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(top_frame, textvariable=user_status_var, style="Section.TLabel").grid(row=0, column=1, sticky="e")

    input_frame = ttk.LabelFrame(form_page, text="Health Inputs")
    input_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
    input_frame.columnconfigure(1, weight=1)
    input_frame.columnconfigure(3, weight=1)

    height_cm_var = tk.StringVar()
    weight_kg_var = tk.StringVar()
    temp_c_var = tk.StringVar()
    blood_group_var = tk.StringVar(value=BLOOD_GROUPS[0])
    hereditary_var = tk.StringVar(value="No")

    ttk.Label(input_frame, text="Height (cm)").grid(row=0, column=0, sticky="w", padx=8, pady=8)
    ttk.Entry(input_frame, textvariable=height_cm_var).grid(row=0, column=1, sticky="ew", padx=8, pady=8)
    ttk.Label(input_frame, text="Weight (kg)").grid(row=0, column=2, sticky="w", padx=8, pady=8)
    ttk.Entry(input_frame, textvariable=weight_kg_var).grid(row=0, column=3, sticky="ew", padx=8, pady=8)

    ttk.Label(input_frame, text="Body Temperature (C)").grid(row=1, column=0, sticky="w", padx=8, pady=8)
    ttk.Entry(input_frame, textvariable=temp_c_var).grid(row=1, column=1, sticky="ew", padx=8, pady=8)
    ttk.Label(input_frame, text="Blood Group").grid(row=1, column=2, sticky="w", padx=8, pady=8)
    ttk.Combobox(input_frame, textvariable=blood_group_var, values=BLOOD_GROUPS, state="readonly").grid(
        row=1, column=3, sticky="ew", padx=8, pady=8
    )

    ttk.Label(input_frame, text="Hereditary Condition").grid(row=2, column=0, sticky="w", padx=8, pady=8)
    ttk.Combobox(input_frame, textvariable=hereditary_var, values=["Yes", "No"], state="readonly").grid(
        row=2, column=1, sticky="ew", padx=8, pady=8
    )

    ttk.Label(input_frame, text="Symptoms (select all that apply)").grid(row=3, column=0, sticky="nw", padx=8, pady=8)
    symptoms_frame = ttk.Frame(input_frame)
    symptoms_frame.grid(row=3, column=1, columnspan=3, sticky="ew", padx=8, pady=8)
    for col in range(3):
        symptoms_frame.columnconfigure(col, weight=1)

    symptom_vars = {}
    for idx, symptom in enumerate(SYMPTOM_OPTIONS):
        var = tk.BooleanVar(value=False)
        symptom_vars[symptom] = var
        r = idx // 3
        c = idx % 3
        ttk.Checkbutton(symptoms_frame, text=symptom, variable=var).grid(row=r, column=c, sticky="w", padx=4, pady=2)

    check_result_button = ttk.Button(input_frame, text="Check Result", command=lambda: calculate_and_save())
    check_result_button.grid(row=4, column=0, columnspan=4, sticky="ew", padx=8, pady=(4, 10))

    output_frame = ttk.LabelFrame(form_page, text="Latest Saved Result")
    output_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
    output_frame.columnconfigure(0, weight=1)

    result_box = tk.Text(output_frame, height=15, wrap="word")
    result_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
    result_box.config(state="disabled")

    storage_var = tk.StringVar(value=f"Stored records: {len(storage.records)}")
    ttk.Label(form_page, textvariable=storage_var).grid(row=3, column=0, sticky="w")

    def set_result_text(text: str):
        result_box.config(state="normal")
        result_box.delete("1.0", "end")
        result_box.insert("1.0", text)
        result_box.config(state="disabled")

    def clear_fields():
        height_cm_var.set("")
        weight_kg_var.set("")
        temp_c_var.set("")
        blood_group_var.set(BLOOD_GROUPS[0])
        hereditary_var.set("No")
        for var in symptom_vars.values():
            var.set(False)
        set_result_text("")

    def calculate_record():
        height_cm = safe_float(height_cm_var.get(), "Height")
        weight_kg = safe_float(weight_kg_var.get(), "Weight")
        temp_c = safe_float(temp_c_var.get(), "Body temperature")

        height_m = height_cm / 100.0
        bmi = weight_kg / (height_m * height_m)
        bmi_status, bmi_advice = classify_bmi(bmi)
        fever_status = check_fever(temp_c)

        symptoms = [name for name, selected in symptom_vars.items() if selected.get()]
        recommended_doctor = doctor_from_symptoms(symptoms, fever_status, bmi_status)
        advice = local_advice(bmi_status, fever_status, symptoms, hereditary_var.get())

        prompt = (
            "You are a health assistant. Give short, safe, non-diagnostic advice and state when to seek urgent care.\n"
            f"Patient BMI: {bmi:.2f} ({bmi_status})\n"
            f"Body temperature: {temp_c:.1f} C ({fever_status})\n"
            f"Symptoms: {', '.join(symptoms) if symptoms else 'None provided'}\n"
            f"Blood group: {blood_group_var.get()}\n"
            f"Hereditary condition: {hereditary_var.get()}\n"
            f"Recommended doctor type: {recommended_doctor}\n"
        )
        web_context = serper_suggestion(prompt)
        ai_suggestion = doctor_style_response(
            bmi_status=bmi_status,
            fever_status=fever_status,
            temp_c=temp_c,
            symptoms=symptoms,
            hereditary_condition=hereditary_var.get(),
            recommended_doctor=recommended_doctor,
            web_context=web_context,
        )

        result = HealthResult(
            bmi=round(bmi, 2),
            bmi_status=bmi_status,
            fever_status=fever_status,
            recommended_doctor=recommended_doctor,
            advice=f"{bmi_advice} {advice}",
            ai_suggestion=ai_suggestion,
        )

        record = HealthRecord(
            created_at=datetime.now().isoformat(timespec="seconds"),
            user=current_user["session"],
            weight_kg=round(weight_kg, 2),
            height_cm=round(height_cm, 2),
            body_temp_c=round(temp_c, 2),
            blood_group=blood_group_var.get(),
            hereditary_condition=hereditary_var.get(),
            symptoms=symptoms,
            result=result,
        )
        return record

    def calculate_and_save():
        if current_user["session"] is None:
            messagebox.showwarning("Login Required", "Please login first.")
            show_page(login_page)
            return
        if active_job["thread"] and active_job["thread"].is_alive():
            messagebox.showinfo("Please wait", "A result is already being generated.")
            return

        loading = tk.Toplevel(root)
        loading.title("Preparing Result")
        loading.geometry("420x170")
        loading.resizable(False, False)
        loading.transient(root)
        loading.grab_set()

        ttk.Label(loading, text="Analyzing symptoms and preparing report...", style="Section.TLabel").pack(
            fill="x", padx=18, pady=(20, 10)
        )
        ttk.Label(loading, text="Please wait").pack(fill="x", padx=18, pady=(0, 8))
        progress = ttk.Progressbar(loading, mode="indeterminate")
        progress.pack(fill="x", padx=18, pady=(0, 16))
        progress.start(10)
        check_result_button.config(state="disabled")

        result_holder = {"record": None, "error": None}

        def worker():
            try:
                result_holder["record"] = calculate_record()
            except Exception as exc:
                result_holder["error"] = exc

        def finalize():
            if thread.is_alive():
                root.after(100, finalize)
                return

            progress.stop()
            loading.destroy()
            check_result_button.config(state="normal")
            active_job["thread"] = None

            if result_holder["error"] is not None:
                err = result_holder["error"]
                if isinstance(err, ValueError):
                    messagebox.showerror("Invalid Input", str(err))
                else:
                    messagebox.showerror("Processing Error", f"Failed to generate result: {err}")
                return

            record = result_holder["record"]
            storage.add(record)
            storage_var.set(f"Stored records: {len(storage.records)}")

            output_text = (
                "HEALTH REPORT\n"
                f"User: {record.user.username}\n"
                f"Date: {record.created_at}\n"
                f"BMI: {record.result.bmi} ({record.result.bmi_status})\n"
                f"Fever Check: {record.result.fever_status}\n"
                f"Recommended Doctor: {record.result.recommended_doctor}\n"
                f"Blood Group: {record.blood_group}\n"
                f"Hereditary Condition: {record.hereditary_condition or 'None'}\n"
                f"Symptoms: {', '.join(record.symptoms) if record.symptoms else 'None'}\n\n"
                f"Advice:\n{record.result.advice}\n\n"
                f"Web Suggestion (Serper):\n{record.result.ai_suggestion}\n"
            )
            set_result_text(output_text)
            messagebox.showinfo("Result Ready", "Your health report is ready.")

        thread = threading.Thread(target=worker, daemon=True)
        active_job["thread"] = thread
        thread.start()
        root.after(100, finalize)

    button_frame = ttk.Frame(form_page)
    button_frame.grid(row=4, column=0, sticky="ew")
    button_frame.columnconfigure(0, weight=1)
    button_frame.columnconfigure(1, weight=1)
    ttk.Button(button_frame, text="Back to Login", command=lambda: show_page(login_page)).grid(
        row=0, column=0, padx=(0, 6), sticky="ew"
    )
    ttk.Button(button_frame, text="Clear", command=clear_fields).grid(row=0, column=1, padx=(6, 6), sticky="ew")
    ttk.Button(button_frame, text="Exit", command=root.destroy).grid(row=0, column=2, padx=(6, 0), sticky="ew")
    button_frame.columnconfigure(2, weight=1)

    show_page(login_page)

    return root


if __name__ == "__main__":
    app = build_app()
    app.mainloop()
