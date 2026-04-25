import json
import tkinter as tk
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
try:
    import google.generativeai as genai
except ImportError:
    genai = None


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
GEMINI_API_KEY = "AIzaSyCkpKH2V37vtyUKsr5DAXpxay09Ak6SAHw"


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


def gemini_suggestion(payload_text: str):
    if genai is None:
        return "Gemini SDK is not installed. Install with: pip install google-generativeai"
    if not GEMINI_API_KEY.strip():
        return "Gemini API key is missing in backend configuration."
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        models = ["gemini-2.0-flash", "gemini-flash-latest", "gemini-2.5-flash"]
        last_error = "Unknown Gemini error."
        for model_name in models:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(payload_text)
                text = (response.text or "").strip()
                if text:
                    return text
                last_error = f"Gemini returned empty response using {model_name}."
            except Exception as model_exc:
                message = str(model_exc)
                if "not found" in message.lower():
                    last_error = f"Model not available: {model_name}."
                    continue
                if "quota" in message.lower() or "resource_exhausted" in message.lower() or "429" in message:
                    return "Gemini quota exceeded for this API key/project. Enable billing or use a key with active quota."
                last_error = message
                continue
        return f"Gemini unavailable right now. {last_error}"
    except Exception as exc:
        return f"Gemini call failed: {exc}"


def build_app():
    storage = HealthStorage(DATA_FILE)
    root = tk.Tk()
    root.title("Health Assistant (BMI + Fever + Symptoms)")
    root.geometry("980x760")
    root.minsize(900, 700)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TLabel", font=("Segoe UI", 10))
    style.configure("Header.TLabel", font=("Segoe UI Semibold", 20))
    style.configure("Section.TLabel", font=("Segoe UI Semibold", 11))
    style.configure("TButton", padding=6)

    container = ttk.Frame(root, padding=16)
    container.pack(fill="both", expand=True)
    container.columnconfigure(0, weight=1)

    ttk.Label(container, text="Health Consultation Assistant", style="Header.TLabel").grid(
        row=0, column=0, sticky="w", pady=(0, 6)
    )
    ttk.Label(container, text="Login, enter health details, and get result based on selected symptoms.").grid(
        row=1, column=0, sticky="w", pady=(0, 14)
    )

    current_user = {"session": None}

    login_frame = ttk.LabelFrame(container, text="Login")
    login_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
    login_frame.columnconfigure(1, weight=1)
    login_frame.columnconfigure(2, weight=1)

    username_var = tk.StringVar()
    login_status_var = tk.StringVar(value="Not logged in")

    ttk.Label(login_frame, text="Username").grid(row=0, column=0, sticky="w", padx=8, pady=8)
    ttk.Entry(login_frame, textvariable=username_var).grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=8)

    def do_login():
        username = username_var.get().strip()
        if not username:
            messagebox.showerror("Login Error", "Username is required.")
            return
        current_user["session"] = UserLogin(username=username)
        login_status_var.set(f"Logged in as {username}")

    ttk.Button(login_frame, text="Login", command=do_login).grid(row=0, column=3, sticky="ew", padx=8, pady=8)
    ttk.Label(login_frame, textvariable=login_status_var).grid(row=1, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 8))

    input_frame = ttk.LabelFrame(container, text="Health Inputs")
    input_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 12))
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

    output_frame = ttk.LabelFrame(container, text="Result")
    output_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 12))
    output_frame.columnconfigure(0, weight=1)

    result_box = tk.Text(output_frame, height=15, wrap="word")
    result_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
    result_box.config(state="disabled")

    storage_var = tk.StringVar(value=f"Stored records: {len(storage.records)}")
    ttk.Label(container, textvariable=storage_var).grid(row=5, column=0, sticky="w")

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

    def calculate_and_save():
        if current_user["session"] is None:
            messagebox.showwarning("Login Required", "Please login first.")
            return

        try:
            height_cm = safe_float(height_cm_var.get(), "Height")
            weight_kg = safe_float(weight_kg_var.get(), "Weight")
            temp_c = safe_float(temp_c_var.get(), "Body temperature")
        except ValueError as exc:
            messagebox.showerror("Invalid Input", str(exc))
            return

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
        ai_suggestion = gemini_suggestion(prompt)

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
            f"Gemini Suggestion:\n{record.result.ai_suggestion}\n"
        )
        set_result_text(output_text)

    button_frame = ttk.Frame(container)
    button_frame.grid(row=6, column=0, sticky="ew")
    button_frame.columnconfigure(0, weight=1)
    button_frame.columnconfigure(1, weight=1)
    ttk.Button(button_frame, text="Clear", command=clear_fields).grid(row=0, column=0, padx=(0, 6), sticky="ew")
    ttk.Button(button_frame, text="Exit", command=root.destroy).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    return root


if __name__ == "__main__":
    app = build_app()
    app.mainloop()
