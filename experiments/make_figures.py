"""Draw the result figures from results/*.json -> results/results_a.png (E1 PR curves, E3 sweep, E3 latency) and results_b.png (E2, E5)."""
import json
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
INK, AMBER, TEAL, GREY = "#16202B", "#B26A00", "#16697A", "#8A94A0"
plt.rcParams.update({"font.size": 6.5, "axes.edgecolor": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.titlesize": 7, "axes.titleweight": "bold"})
R = Path("results"); load = lambda n: json.load(open(R / n)) if (R / n).exists() else None
e1, e2, e3, e5 = load("e1.json"), load("e2.json"), load("e3.json"), load("e5.json")
proxy = any(x and x.get("label_source") != "L2" for x in (e1, e2, e3, e5) if x)
tag = "  [PROXY]" if proxy else ""
fig, ax = plt.subplots(1, 3, figsize=(7.3, 2.45))
if e1:
    for name, c, ls, lab in [("xgb", AMBER, "-", "XGBoost"), ("lr", TEAL, "--", "Logistic reg."), ("rf", GREY, ":", "Random forest")]:
        prec_, rec_ = e1["pr_curves"][name]; ax[0].plot(rec_, prec_, color=c, ls=ls, lw=1.2, label=lab)   # (precision, recall) order from sklearn
    ax[0].axhline(e1["majority_pr_auc"], color=INK, lw=0.8, ls="-.", label="Majority (chance)")
    ax[0].set_xlabel("Recall"); ax[0].set_ylabel("Precision"); ax[0].set_title("E1  PR curve" + tag); ax[0].legend(frameon=False, fontsize=5.5); ax[0].set_ylim(0, 1.02)
if e3:
    sw = e3["tau_sweep"]; t = [s["tau"] for s in sw]
    ax[1].plot(t, [s["precision"] if s["precision"] is not None else np.nan for s in sw], color=AMBER, lw=1.3, label="Precision")
    ax[1].plot(t, [s["recall"] if s["recall"] is not None else np.nan for s in sw], color=TEAL, lw=1.3, ls="--", label="Recall")
    ax[1].plot(t, [s["spec_fail_rate_k0"] for s in sw], color=INK, lw=1.0, ls=":", label="Specs failing gate (k=0)")
    ax[1].set_xlabel("Threshold $\\tau$"); ax[1].set_title("E3  threshold sweep" + tag); ax[1].legend(frameon=False, fontsize=5.5); ax[1].set_ylim(0, 1.02)
    if "latency" in e3:
        L = e3["latency"]["rows"]; bins = [(10, 50), (50, 100), (100, 250), (250, 500)]; xs = np.arange(4); bot = np.zeros(4)
        for cname, col, lab in [("s1", AMBER, "S1 Spectral"), ("s0", TEAL, "S0"), ("s2a", INK, "S2a"), ("s2b", GREY, "S2b"), ("s2c", "#C9CED4", "S2c (SHAP)")]:
            v = np.array([np.median([r[cname] for r in L if lo <= r["n_endpoints"] < hi] or [0]) for lo, hi in bins])
            ax[2].bar(xs, v, bottom=bot, color=col, label=lab, width=0.6); bot += v
        ax[2].set_xticks(xs); ax[2].set_xticklabels(["%d-%d" % b for b in bins]); ax[2].set_xlabel("Endpoints per specification")
        ax[2].set_ylabel("Seconds (median)"); ax[2].set_title("E3  runtime per scan"); ax[2].legend(frameon=False, fontsize=5.2)
fig.tight_layout(); fig.savefig(R / "results_a.png", dpi=300); plt.close(fig)
fig, ax = plt.subplots(1, 3, figsize=(7.3, 2.6), gridspec_kw={"width_ratios": [1.1, 0.8, 1.2]})
if e2:
    cats = [c for c, v in e2["categories"].items() if "skipped" not in v]; x = np.arange(len(cats)); w = 0.27
    ax[0].bar(x - w, [e2["categories"][c]["prevalence"] for c in cats], w, color=GREY, label="Chance (prevalence)")
    ax[0].bar(x, [e2["categories"][c]["pr_auc_heldout"] for c in cats], w, color=AMBER, label="Category held out")
    ax[0].bar(x + w, [e2["categories"][c]["pr_auc_reference"] for c in cats], w, color=TEAL, label="Category included")
    ax[0].set_xticks(x); ax[0].set_xticklabels(cats); ax[0].set_ylabel("PR-AUC"); ax[0].set_title("E2  rule hold-out" + tag); ax[0].legend(frameon=False, fontsize=5.3)
if e5:
    ab = e5["ablation_pr_auc"]; base = ab["none"][0]; keys = [k for k in ab if k != "none"]
    ax[1].barh(keys, [base - ab[k][0] for k in keys], color=AMBER); ax[1].invert_yaxis(); ax[1].axvline(0, color=INK, lw=0.6)
    ax[1].set_xlabel("PR-AUC lost when group removed"); ax[1].set_title("E5  ablation" + tag)
    top = e5["shap_global"][:12][::-1]; cc = {"A": INK, "B": AMBER, "C": TEAL, "D": GREY, "E": "#7A3E00", "F": "#C9CED4"}
    ax[2].barh([t[0] for t in top], [t[1] for t in top], color=[cc.get(t[2], GREY) for t in top]); ax[2].set_xlabel("Mean |SHAP| (log-odds)")
    ax[2].set_title("E5  top features (colour = group)"); ax[2].tick_params(axis="y", labelsize=5.5)
fig.tight_layout(); fig.savefig(R / "results_b.png", dpi=300); plt.close(fig); print("figures written to results/")
