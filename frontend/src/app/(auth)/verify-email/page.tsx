"use client";

import React, { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/authContext";
import { CheckCircle2, Mail, ArrowRight, RefreshCw, ShieldCheck } from "lucide-react";

export default function VerifyEmailPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();

  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [isVerified, setIsVerified] = useState(false);
  const [error, setError] = useState("");
  const [infoMessage, setInfoMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [countdown, setCountdown] = useState(60);

  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = sessionStorage.getItem("verify_email") || "";
      setEmail(stored);
    }

    const timer = setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleChange = (index: number, value: string) => {
    const digits = value.replace(/\D/g, "");
    if (digits.length > 1) {
      const next = ["", "", "", "", "", ""];
      digits.slice(0, 6).split("").forEach((ch, idx) => {
        next[idx] = ch;
      });
      setOtp(next);
      const focusIdx = Math.min(5, digits.length - 1);
      inputRefs.current[focusIdx]?.focus();
      return;
    }

    const newOtp = [...otp];
    newOtp[index] = digits;
    setOtp(newOtp);

    if (digits && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handleVerify = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (loading || resending) return;
    const code = otp.join("").trim();
    if (code.length < 6) {
      setError("Please enter the 6-digit verification code from the backend terminal.");
      return;
    }
    if (!email) {
      setError("No email address found for verification. Please register again.");
      return;
    }
    setError("");
    setInfoMessage("");
    setLoading(true);

    try {
      await api.verifyEmail({ email, code });
      setIsVerified(true);
      setTimeout(() => {
        router.push("/login");
      }, 1500);
    } catch (err: any) {
      setError(err.message || "Invalid or expired verification code.");
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (resending || loading || countdown > 0) return;
    if (!email) {
      setError("No email address found for verification. Please register or log in again.");
      return;
    }
    setError("");
    setInfoMessage("");
    setResending(true);
    try {
      const res = await api.resendOtp({ email, purpose: "VERIFY" });
      setOtp(["", "", "", "", "", ""]);
      setCountdown(60);
      setInfoMessage(res.message || "A new 6-digit code was generated. Check the backend terminal.");
      inputRefs.current[0]?.focus();
    } catch (err: any) {
      setError(err.message || "Failed to resend verification code.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-[calc(100dvh-4rem)] flex items-center justify-center p-3 sm:p-4 bg-gradient-to-b from-slate-50 via-slate-100/50 to-indigo-50/30 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950 transition-colors">
      <div className="w-full max-w-md bg-white dark:bg-slate-900 rounded-3xl border border-slate-200/80 dark:border-slate-800 p-5 sm:p-8 shadow-elevated text-center transition-colors">

        {isVerified ? (
          <div className="py-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mx-auto border border-emerald-200 dark:border-emerald-800">
              <CheckCircle2 className="w-10 h-10" />
            </div>
            <h2 className="text-2xl font-extrabold text-slate-900 dark:text-white">Account Verified! ✓</h2>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Your account is now active. Redirecting to login...
            </p>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 rounded-full text-xs font-bold border border-emerald-200 dark:border-emerald-800">
              <ShieldCheck className="w-4 h-4" /> Verified Account Active
            </div>
          </div>
        ) : (
          <div>
            <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mx-auto mb-3 border border-indigo-100 dark:border-indigo-900/50 shadow-xs">
              <Mail className="w-6 h-6" />
            </div>
            <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white">Verify Your Account</h1>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
              Enter the 6-digit verification code to verify your account.
              {email && (
                <span className="block font-bold text-slate-700 dark:text-slate-200 mt-1 break-all">{email}</span>
              )}
            </p>

            <div className="p-2.5 my-4 bg-indigo-50/60 dark:bg-indigo-950/40 rounded-xl border border-indigo-100 dark:border-indigo-900 text-xs text-indigo-900 dark:text-indigo-300">
              Development mode: Check the backend terminal for your verification code.
            </div>

            {infoMessage && (
              <div className="p-3 mb-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                {infoMessage}
              </div>
            )}

            {error && (
              <div className="p-3 mb-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-xs font-semibold text-rose-700 dark:text-rose-400">
                {error}
              </div>
            )}

            <form onSubmit={handleVerify} className="space-y-6">
              {/* 6-box OTP */}
              <div className="flex justify-center gap-1.5 sm:gap-3">
                {otp.map((digit, idx) => (
                  <input
                    key={idx}
                    ref={(el) => { inputRefs.current[idx] = el; }}
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={digit}
                    disabled={loading}
                    onChange={(e) => handleChange(idx, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(idx, e)}
                    aria-label={`Verification digit ${idx + 1}`}
                    className="w-10 h-12 sm:w-11 sm:h-12 text-center text-lg sm:text-xl font-extrabold bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:bg-white dark:focus:bg-slate-900 focus:outline-none focus:border-indigo-600 focus:ring-2 focus:ring-indigo-100 dark:focus:ring-indigo-950 transition-all text-slate-800 dark:text-white disabled:opacity-60"
                  />
                ))}
              </div>

              <div className="flex flex-col gap-3">
                <button
                  type="submit"
                  disabled={loading || resending}
                  className="w-full py-3 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs shadow-md shadow-indigo-200 dark:shadow-none transition-all flex items-center justify-center gap-2 disabled:opacity-60"
                >
                  {loading ? "Verifying..." : "Verify Account"}
                  <ArrowRight className="w-4 h-4" />
                </button>

                <button
                  type="button"
                  disabled={countdown > 0 || resending || loading}
                  onClick={handleResend}
                  className="text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors flex items-center justify-center gap-1 disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${resending ? "animate-spin" : ""}`} />
                  {resending
                    ? "Generating New Code..."
                    : countdown > 0
                    ? `Resend OTP in ${countdown}s`
                    : "Resend OTP"}
                </button>
              </div>
            </form>
          </div>
        )}

      </div>
    </div>
  );
}
