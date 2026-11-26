"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { api } from "@/lib/api";
import {
  Mic, Sparkles, CheckCircle2, ArrowRight,
  RefreshCw, Award, Target, HelpCircle, Send, Check, AlertTriangle
} from "lucide-react";

export default function MockInterviewPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-xs">Loading Mock Interview Simulator...</div>}>
      <MockInterviewContent />
    </Suspense>
  );
}

function MockInterviewContent() {
  const searchParams = useSearchParams();
  const initialJobId = searchParams.get("job_id");

  const [jobs, setJobs] = useState<any[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number>(Number(initialJobId) || 1);
  const [difficulty, setDifficulty] = useState("Intermediate");
  const [interviewType, setInterviewType] = useState("Mixed");

  const [questions, setQuestions] = useState<any[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<any>(null);

  useEffect(() => {
    loadJobs();
  }, []);

  const loadJobs = async () => {
    try {
      const data = await api.getJobs();
      setJobs(data.jobs || []);
      fetchQuestions(Number(initialJobId) || 1, difficulty, interviewType);
    } catch (e: any) {
      setError(e.message || "Failed to load jobs.");
    }
  };

  const fetchQuestions = async (jId: number, diff: string, type: string) => {
    setLoadingQuestions(true);
    setReport(null);
    setError(null);
    setAnswers({});
    try {
      const res = await api.getMockInterviewQuestions({
        job_id: jId,
        difficulty: diff,
        interview_type: type
      });
      setQuestions(res.questions || []);
    } catch (e: any) {
      setError(e.message || "Failed to load interview questions.");
      setQuestions([]);
    } finally {
      setLoadingQuestions(false);
    }
  };

  const handleEvaluate = async () => {
    setError(null);
    const missingIds = questions
      .filter((q) => !(answers[q.id] || "").trim())
      .map((q, i) => `Question ${i + 1}`);

    if (missingIds.length > 0) {
      setError(`Please provide your own answer before submitting (${missingIds.join(", ")} ${missingIds.length === 1 ? "is" : "are"} empty).`);
      return;
    }

    setEvaluating(true);
    try {
      const formatted = questions.map((q) => ({
        question_id: q.id,
        question: q.question,
        category: q.category,
        user_answer: (answers[q.id] || "").trim(),
      }));
      const res = await api.evaluateInterviewAnswers(formatted);
      setReport(res);
    } catch (e: any) {
      setError(e.message || "Failed to evaluate interview answers.");
      setReport(null);
    } finally {
      setEvaluating(false);
    }
  };

  return (
    <div className="flex-1 flex flex-row min-h-screen bg-slate-50 dark:bg-slate-950 transition-colors">
      <Sidebar />

      <div className="flex-1 min-w-0 p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto w-full space-y-6">

        {/* Header */}
        <div>
          <span className="text-xs font-bold uppercase tracking-widest text-indigo-600 dark:text-indigo-400 block mb-1">
            Interactive AI Evaluator
          </span>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
            AI Mock Interview Simulator
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-1">
            Dynamic questions formulated from your resume, target job requirements, and detected skill gaps.
          </p>
        </div>

        {/* Setup Configuration */}
        <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-6 shadow-xs space-y-4">
          <div className="grid sm:grid-cols-3 gap-4">

            {/* Target Job */}
            <div>
              <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">Target Job</label>
              <select
                value={selectedJobId}
                onChange={(e) => setSelectedJobId(Number(e.target.value))}
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-semibold text-slate-800 dark:text-slate-200 focus:outline-none focus:border-indigo-600"
              >
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>{j.title} ({j.company_name})</option>
                ))}
              </select>
            </div>

            {/* Difficulty */}
            <div>
              <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">Difficulty</label>
              <div className="grid grid-cols-3 gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-xl">
                {["Beginner", "Intermediate", "Advanced"].map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDifficulty(d)}
                    className={`py-1.5 text-xs font-bold rounded-lg transition-all ${
                      difficulty === d ? "bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-300 shadow-2xs" : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>

            {/* Interview Type */}
            <div>
              <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">Type</label>
              <div className="grid grid-cols-3 gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-xl">
                {["Technical", "Behavioral", "Mixed"].map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setInterviewType(t)}
                    className={`py-1.5 text-xs font-bold rounded-lg transition-all ${
                      interviewType === t ? "bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-300 shadow-2xs" : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={() => fetchQuestions(selectedJobId, difficulty, interviewType)}
              disabled={loadingQuestions}
              className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold flex items-center gap-2 shadow-xs transition-all"
            >
              {loadingQuestions ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              <span>Generate Questions</span>
            </button>
          </div>
        </div>

        {/* Questions & Answering Form */}
        <div className="space-y-4">
          {questions.map((q, idx) => (
            <div key={q.id} className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-6 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-extrabold ${
                  q.category === 'Skill Gap' ? 'bg-amber-100 text-amber-900 dark:bg-amber-950/60 dark:text-amber-300 border border-amber-200 dark:border-amber-800' :
                  q.category === 'Technical' ? 'bg-indigo-100 text-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800' : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200'
                }`}>
                  Question {idx + 1} • {q.category}
                </span>
                <span className="text-[11px] text-slate-400 dark:text-slate-500 font-semibold">{q.context}</span>
              </div>

              <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                "{q.question}"
              </h3>

              <textarea
                rows={4}
                value={answers[q.id] || ""}
                onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                className="w-full p-3 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl text-xs font-medium text-slate-800 dark:text-slate-200 focus:bg-white dark:focus:bg-slate-900 focus:outline-none focus:border-indigo-600"
                placeholder="Type your response here..."
              ></textarea>

              <div className="text-[11px] text-slate-400 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/60 p-2.5 rounded-xl border border-slate-100 dark:border-slate-800 flex items-start gap-1.5">
                <HelpCircle className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400 shrink-0 mt-0.5" />
                <span><strong>Hint:</strong> {q.sample_answer_hint}</span>
              </div>
            </div>
          ))}

          {questions.length > 0 && (
            <div className="flex justify-end pt-2">
              <button
                onClick={handleEvaluate}
                disabled={evaluating}
                className="w-full sm:w-auto justify-center px-6 sm:px-8 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-md flex items-center gap-2 transition-all disabled:opacity-60"
              >
                {evaluating ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                <span>{evaluating ? "Evaluating Answers..." : "Submit Answers & Generate Score Report"}</span>
              </button>
            </div>
          )}

          {error && (
            <div className="p-4 rounded-2xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-xs font-semibold text-rose-800 dark:text-rose-200 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {/* Evaluation Report */}
        {report && (
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-6 sm:p-8 shadow-elevated space-y-6 animate-in fade-in">
            <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-100 dark:border-slate-800">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
                    Evaluation Scorecard
                  </span>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                    report.evaluation_mode === "llm"
                      ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800"
                      : "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800"
                  }`}>
                    {report.evaluation_mode === "llm" ? "LLM Evaluator" : "Deterministic Rubric Fallback"}
                  </span>
                </div>
                <h3 className="text-xl font-extrabold text-slate-900 dark:text-white">Interview Performance Report</h3>
                {report.evaluation_note && (
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">{report.evaluation_note}</p>
                )}
              </div>
              <div className="text-right">
                <span className="text-3xl font-extrabold text-indigo-600 dark:text-indigo-400 leading-none">{report.overall_score}%</span>
                <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase block mt-0.5">Overall Score</span>
              </div>
            </div>

            {/* Pillar Scores */}
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-3.5 bg-slate-50 dark:bg-slate-800/80 rounded-2xl border border-slate-200 dark:border-slate-700">
                <span className="text-xl font-extrabold text-slate-900 dark:text-white">{report.technical_score}%</span>
                <span className="text-[10px] uppercase font-bold text-slate-400 dark:text-slate-400 block mt-1">Technical Rigor</span>
              </div>
              <div className="p-3.5 bg-slate-50 dark:bg-slate-800/80 rounded-2xl border border-slate-200 dark:border-slate-700">
                <span className="text-xl font-extrabold text-slate-900 dark:text-white">{report.communication_score}%</span>
                <span className="text-[10px] uppercase font-bold text-slate-400 dark:text-slate-400 block mt-1">Communication</span>
              </div>
              <div className="p-3.5 bg-slate-50 dark:bg-slate-800/80 rounded-2xl border border-slate-200 dark:border-slate-700">
                <span className="text-xl font-extrabold text-slate-900 dark:text-white">{report.problem_solving_score}%</span>
                <span className="text-[10px] uppercase font-bold text-slate-400 dark:text-slate-400 block mt-1">Problem Solving</span>
              </div>
            </div>

            <p className="text-xs text-slate-700 dark:text-slate-300 bg-indigo-50/60 dark:bg-indigo-950/40 p-3.5 rounded-2xl border border-indigo-100 dark:border-indigo-900/60 leading-relaxed font-medium">
              {report.summary}
            </p>

            {/* Strength Areas, Weak Areas & Recommended Topics */}
            <div className="grid md:grid-cols-3 gap-4 text-xs">
              <div className="p-4 bg-emerald-50/50 dark:bg-emerald-950/30 rounded-2xl border border-emerald-100 dark:border-emerald-900/40 space-y-2">
                <span className="text-xs font-extrabold text-emerald-900 dark:text-emerald-300 uppercase tracking-wider block">
                  Strength Areas:
                </span>
                {report.strength_areas?.map((s: string, i: number) => (
                  <div key={i} className="flex items-start gap-1.5 text-slate-700 dark:text-slate-300">
                    <span className="text-emerald-500 font-bold">•</span>
                    <span>{s}</span>
                  </div>
                ))}
              </div>

              <div className="p-4 bg-rose-50/50 dark:bg-rose-950/30 rounded-2xl border border-rose-100 dark:border-rose-900/40 space-y-2">
                <span className="text-xs font-extrabold text-rose-900 dark:text-rose-300 uppercase tracking-wider block">
                  Weak Areas to Polish:
                </span>
                {report.weak_areas?.map((w: string, i: number) => (
                  <div key={i} className="flex items-start gap-1.5 text-slate-700 dark:text-slate-300">
                    <span className="text-rose-500 font-bold">•</span>
                    <span>{w}</span>
                  </div>
                ))}
              </div>

              <div className="p-4 bg-indigo-50/50 dark:bg-indigo-950/30 rounded-2xl border border-indigo-100 dark:border-indigo-900/40 space-y-2">
                <span className="text-xs font-extrabold text-indigo-900 dark:text-indigo-300 uppercase tracking-wider block">
                  Recommended Study Topics:
                </span>
                {report.recommended_topics?.map((r: string, i: number) => (
                  <div key={i} className="flex items-start gap-1.5 text-slate-700 dark:text-slate-300">
                    <span className="text-indigo-600 dark:text-indigo-400 font-bold">•</span>
                    <span>{r}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Per-Question Detailed Feedback */}
            {report.question_evaluations && report.question_evaluations.length > 0 && (
              <div className="space-y-4 pt-2 border-t border-slate-100 dark:border-slate-800">
                <h4 className="text-sm font-extrabold text-slate-900 dark:text-white uppercase tracking-wider">
                  Per-Question Feedback & Review
                </h4>
                {report.question_evaluations.map((qe: any, idx: number) => (
                  <div key={qe.question_id || idx} className="p-5 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 space-y-3 text-xs">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <span className="text-[10px] font-bold uppercase text-indigo-600 dark:text-indigo-400 block">
                          Question {idx + 1} • {qe.category}
                        </span>
                        <p className="font-bold text-slate-900 dark:text-white text-sm mt-0.5">"{qe.question}"</p>
                      </div>
                      <span className="text-lg font-extrabold text-indigo-600 dark:text-indigo-400 shrink-0">
                        {qe.score}%
                      </span>
                    </div>

                    <div className="p-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                      <span className="text-[10px] font-bold uppercase text-slate-400 block mb-1">Your Submitted Answer</span>
                      <p className="text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{qe.user_answer}</p>
                    </div>

                    {qe.criteria_scores && (
                      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-center">
                        {Object.entries(qe.criteria_scores).map(([k, v]: [string, any]) => (
                          <div key={k} className="p-2 rounded-xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
                            <span className="text-sm font-extrabold text-slate-900 dark:text-white">{v}%</span>
                            <span className="text-[9px] font-bold uppercase text-slate-400 block truncate">{k.replace(/_/g, " ")}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    <p className="text-slate-600 dark:text-slate-300">
                      <strong>Score Explanation:</strong> {qe.score_explanation}
                    </p>

                    <div className="grid sm:grid-cols-2 gap-3">
                      <div>
                        <span className="font-bold text-emerald-700 dark:text-emerald-400 block mb-1">Strengths</span>
                        <ul className="space-y-1 text-slate-700 dark:text-slate-300">
                          {qe.strengths?.map((s: string, i: number) => (
                            <li key={i}>• {s}</li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <span className="font-bold text-rose-700 dark:text-rose-400 block mb-1">Missing Concepts / Weak Areas</span>
                        <ul className="space-y-1 text-slate-700 dark:text-slate-300">
                          {(qe.missing_concepts?.length ? qe.missing_concepts : qe.weak_areas)?.map((m: string, i: number) => (
                            <li key={i}>• {m}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {qe.suggested_improved_answer && (
                      <div className="p-3 rounded-xl bg-emerald-50/50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800">
                        <span className="text-[10px] font-bold uppercase text-emerald-700 dark:text-emerald-300 block mb-1">
                          Suggested Improved Answer
                        </span>
                        <p className="text-slate-800 dark:text-slate-200">{qe.suggested_improved_answer}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

          </div>
        )}

      </div>
    </div>
  );
}
