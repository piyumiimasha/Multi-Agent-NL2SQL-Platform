-- Schema reference for the MediCore hospital database.
-- This file is used as an offline fallback for prompt construction and previewing.

CREATE TABLE public.departments (
  department_id integer NOT NULL DEFAULT nextval('departments_department_id_seq'::regclass),
  department_name character varying NOT NULL UNIQUE,
  location character varying,
  phone character varying,
  head_of_department character varying,
  CONSTRAINT departments_pkey PRIMARY KEY (department_id)
);

CREATE TABLE public.specialties (
  specialty_id integer NOT NULL DEFAULT nextval('specialties_specialty_id_seq'::regclass),
  specialty_name character varying NOT NULL UNIQUE,
  description text,
  CONSTRAINT specialties_pkey PRIMARY KEY (specialty_id)
);

CREATE TABLE public.doctors (
  doctor_id integer NOT NULL DEFAULT nextval('doctors_doctor_id_seq'::regclass),
  first_name character varying NOT NULL,
  last_name character varying NOT NULL,
  email character varying UNIQUE,
  phone character varying,
  specialty_id integer NOT NULL,
  department_id integer NOT NULL,
  hire_date date NOT NULL,
  license_number character varying UNIQUE,
  is_active boolean DEFAULT true,
  CONSTRAINT doctors_pkey PRIMARY KEY (doctor_id),
  CONSTRAINT doctors_specialty_id_fkey FOREIGN KEY (specialty_id) REFERENCES public.specialties(specialty_id),
  CONSTRAINT doctors_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(department_id)
);

CREATE TABLE public.staff (
  staff_id integer NOT NULL DEFAULT nextval('staff_staff_id_seq'::regclass),
  first_name character varying NOT NULL,
  last_name character varying NOT NULL,
  role character varying NOT NULL,
  department_id integer NOT NULL,
  email character varying,
  phone character varying,
  hire_date date NOT NULL,
  is_active boolean DEFAULT true,
  CONSTRAINT staff_pkey PRIMARY KEY (staff_id),
  CONSTRAINT staff_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(department_id)
);

CREATE TABLE public.patients (
  patient_id integer NOT NULL DEFAULT nextval('patients_patient_id_seq'::regclass),
  first_name character varying NOT NULL,
  last_name character varying NOT NULL,
  date_of_birth date NOT NULL,
  gender character varying NOT NULL,
  email character varying,
  phone character varying,
  address character varying,
  city character varying,
  blood_type character varying,
  emergency_contact_name character varying,
  emergency_contact_phone character varying,
  registered_date date NOT NULL,
  CONSTRAINT patients_pkey PRIMARY KEY (patient_id)
);

CREATE TABLE public.appointments (
  appointment_id integer NOT NULL DEFAULT nextval('appointments_appointment_id_seq'::regclass),
  patient_id integer NOT NULL,
  doctor_id integer NOT NULL,
  appointment_date date NOT NULL,
  appointment_time time without time zone NOT NULL,
  status character varying NOT NULL DEFAULT 'Scheduled'::character varying,
  reason character varying,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT appointments_pkey PRIMARY KEY (appointment_id),
  CONSTRAINT appointments_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(patient_id),
  CONSTRAINT appointments_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(doctor_id)
);

CREATE TABLE public.admissions (
  admission_id integer NOT NULL DEFAULT nextval('admissions_admission_id_seq'::regclass),
  patient_id integer NOT NULL,
  doctor_id integer NOT NULL,
  department_id integer NOT NULL,
  admission_date date NOT NULL,
  discharge_date date,
  room_number character varying,
  bed_number character varying,
  admission_type character varying NOT NULL,
  status character varying NOT NULL DEFAULT 'Active'::character varying,
  CONSTRAINT admissions_pkey PRIMARY KEY (admission_id),
  CONSTRAINT admissions_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(patient_id),
  CONSTRAINT admissions_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(doctor_id),
  CONSTRAINT admissions_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(department_id)
);

CREATE TABLE public.diagnoses (
  diagnosis_id integer NOT NULL DEFAULT nextval('diagnoses_diagnosis_id_seq'::regclass),
  admission_id integer NOT NULL,
  patient_id integer NOT NULL,
  doctor_id integer NOT NULL,
  diagnosis_code character varying NOT NULL,
  diagnosis_description character varying NOT NULL,
  diagnosis_date date NOT NULL,
  severity character varying NOT NULL,
  CONSTRAINT diagnoses_pkey PRIMARY KEY (diagnosis_id),
  CONSTRAINT diagnoses_admission_id_fkey FOREIGN KEY (admission_id) REFERENCES public.admissions(admission_id),
  CONSTRAINT diagnoses_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(patient_id),
  CONSTRAINT diagnoses_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(doctor_id)
);

CREATE TABLE public.lab_orders (
  lab_order_id integer NOT NULL DEFAULT nextval('lab_orders_lab_order_id_seq'::regclass),
  appointment_id integer NOT NULL,
  patient_id integer NOT NULL,
  doctor_id integer NOT NULL,
  test_name character varying NOT NULL,
  test_category character varying NOT NULL,
  order_date date NOT NULL,
  result_date date,
  result_value character varying,
  result_status character varying,
  notes text,
  CONSTRAINT lab_orders_pkey PRIMARY KEY (lab_order_id),
  CONSTRAINT lab_orders_appointment_id_fkey FOREIGN KEY (appointment_id) REFERENCES public.appointments(appointment_id),
  CONSTRAINT lab_orders_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(patient_id),
  CONSTRAINT lab_orders_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(doctor_id)
);

CREATE TABLE public.prescriptions (
  prescription_id integer NOT NULL DEFAULT nextval('prescriptions_prescription_id_seq'::regclass),
  appointment_id integer NOT NULL,
  patient_id integer NOT NULL,
  doctor_id integer NOT NULL,
  medication_name character varying NOT NULL,
  dosage character varying NOT NULL,
  frequency character varying NOT NULL,
  duration_days integer NOT NULL,
  prescribed_date date NOT NULL,
  notes text,
  CONSTRAINT prescriptions_pkey PRIMARY KEY (prescription_id),
  CONSTRAINT prescriptions_appointment_id_fkey FOREIGN KEY (appointment_id) REFERENCES public.appointments(appointment_id),
  CONSTRAINT prescriptions_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(patient_id),
  CONSTRAINT prescriptions_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(doctor_id)
);

CREATE TABLE public.billing_invoices (
  invoice_id integer NOT NULL DEFAULT nextval('billing_invoices_invoice_id_seq'::regclass),
  patient_id integer NOT NULL,
  admission_id integer,
  invoice_date date NOT NULL,
  total_amount numeric NOT NULL,
  discount numeric DEFAULT 0.00,
  tax numeric DEFAULT 0.00,
  net_amount numeric NOT NULL,
  status character varying NOT NULL DEFAULT 'Pending'::character varying,
  due_date date NOT NULL,
  CONSTRAINT billing_invoices_pkey PRIMARY KEY (invoice_id),
  CONSTRAINT billing_invoices_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(patient_id),
  CONSTRAINT billing_invoices_admission_id_fkey FOREIGN KEY (admission_id) REFERENCES public.admissions(admission_id)
);

CREATE TABLE public.payments (
  payment_id integer NOT NULL DEFAULT nextval('payments_payment_id_seq'::regclass),
  invoice_id integer NOT NULL,
  patient_id integer NOT NULL,
  payment_date date NOT NULL,
  amount numeric NOT NULL,
  payment_method character varying NOT NULL,
  transaction_reference character varying,
  status character varying NOT NULL DEFAULT 'Completed'::character varying,
  CONSTRAINT payments_pkey PRIMARY KEY (payment_id),
  CONSTRAINT payments_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.billing_invoices(invoice_id),
  CONSTRAINT payments_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(patient_id)
);