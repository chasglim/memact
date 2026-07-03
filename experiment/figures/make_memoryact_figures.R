suppressPackageStartupMessages({
  library(ggplot2)
  library(patchwork)
  library(jsonlite)
  library(svglite)
  library(ragg)
})

script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_path <- if (length(script_arg) > 0) sub("^--file=", "", script_arg[[1]]) else "experiment/figures/make_memoryact_figures.R"
root <- normalizePath(file.path(dirname(script_path), "../.."), mustWork = FALSE)
if (!dir.exists(file.path(root, "experiment", "results"))) {
  root <- normalizePath(file.path(dirname(script_path), "../../.."), mustWork = FALSE)
}
if (dir.exists(file.path(root, "paper", "experiment", "results"))) {
  results_dir <- file.path(root, "paper", "experiment", "results")
  figure_dir <- file.path(root, "paper", "figures")
} else {
  results_dir <- file.path(root, "experiment", "results")
  figure_dir <- file.path(root, "figures")
}
dir.create(figure_dir, recursive = TRUE, showWarnings = FALSE)

method_levels <- c("SimTopK", "Sim+Recency", "CapsuleFilter", "ToolGuardOnly", "PairwiseGate", "MemAct-Lite", "MemAct-Strict")
tradeoff_levels <- c("SimTopK", "Sim+Recency", "CapsuleFilter", "ToolGuardOnly", "PairwiseGate", "MemAct-Lite")
failure_method_levels <- c("SimTopK", "CapsuleFilter", "ToolGuardOnly", "MemAct-Lite")
method_labels <- c(
  "SimTopK" = "DirectInject",
  "Sim+Recency" = "Sim+Recency",
  "CapsuleFilter" = "CapsuleFilter",
  "ToolGuardOnly" = "ToolGuardOnly",
  "PairwiseGate" = "PairwiseGate",
  "MemAct-Lite" = "MemAct-Lite",
  "MemAct-Strict" = "MemAct-Strict"
)
method_labels_short <- c(
  "SimTopK" = "Direct",
  "Sim+Recency" = "Recency",
  "CapsuleFilter" = "Capsule",
  "ToolGuardOnly" = "Guard",
  "PairwiseGate" = "Pairwise",
  "MemAct-Lite" = "MemAct",
  "MemAct-Strict" = "Strict"
)
method_palette <- c(
  "SimTopK" = "#8D99A6",
  "Sim+Recency" = "#B6C2CF",
  "CapsuleFilter" = "#6F91B5",
  "ToolGuardOnly" = "#D99765",
  "PairwiseGate" = "#7A68A6",
  "MemAct-Lite" = "#2A8C80",
  "MemAct-Strict" = "#0E5F59"
)
failure_levels <- c("Unsafe MIAD", "CTMIR", "PVAR", "UTIR", "SMMR")
scenario_levels <- c("dev", "office", "compliance")
scenario_labels <- c("dev" = "Cloud Dev", "office" = "Cloud Office", "compliance" = "Cloud Compliance")

theme_set(
  theme_classic(base_size = 6.1, base_family = "Helvetica") +
    theme(
      axis.line = element_line(linewidth = 0.28, colour = "#20242A"),
      axis.ticks = element_line(linewidth = 0.22, colour = "#20242A"),
      axis.text = element_text(colour = "#20242A"),
      legend.title = element_text(size = 5.3),
      legend.text = element_text(size = 4.9),
      legend.key.size = grid::unit(2.25, "mm"),
      legend.spacing.x = grid::unit(0.35, "mm"),
      strip.background = element_blank(),
      strip.text = element_text(size = 5.8, face = "bold"),
      plot.title = element_text(size = 6.4, face = "bold", margin = margin(b = 0.8)),
      panel.grid.major.y = element_line(linewidth = 0.18, colour = "#E6E8EB"),
      panel.grid.major.x = element_line(linewidth = 0.15, colour = "#EEF0F2"),
      panel.grid.minor = element_blank()
    )
)

read_results <- function(name) read.csv(file.path(results_dir, name), check.names = FALSE)

wilson <- function(k, n, z = 1.96) {
  if (n == 0) return(c(0, 0))
  p <- k / n
  den <- 1 + z^2 / n
  center <- (p + z^2 / (2 * n)) / den
  half <- z * sqrt((p * (1 - p) + z^2 / (4 * n)) / n) / den
  c(max(0, center - half), min(1, center + half))
}

save_pub_r <- function(plot, filename, width_mm, height_mm, dpi = 600) {
  w <- width_mm / 25.4
  h <- height_mm / 25.4
  svglite::svglite(file.path(figure_dir, paste0(filename, ".svg")), width = w, height = h)
  print(plot)
  dev.off()
  grDevices::cairo_pdf(file.path(figure_dir, paste0(filename, ".pdf")), width = w, height = h, family = "Helvetica")
  print(plot)
  dev.off()
  ragg::agg_tiff(file.path(figure_dir, paste0(filename, ".tiff")), width = w, height = h, units = "in", res = dpi, compression = "lzw")
  print(plot)
  dev.off()
}

main <- read_results("table_ii_main_results.csv")
main$Method <- factor(main$Method, levels = method_levels)
scenario <- read_results("table_iii_scenario_results.csv")
scenario$Method <- factor(scenario$Method, levels = method_levels)
scenario$Scenario <- factor(scenario$Scenario, levels = scenario_levels, labels = scenario_labels[scenario_levels])
ablation <- read_results("table_iv_ablation.csv")
overhead <- read_results("table_v_overhead.csv")
overhead$Method <- factor(overhead$Method, levels = method_levels)
sensitivity <- read_results("table_vi_candidate_sensitivity.csv")
sensitivity$Method <- factor(sensitivity$Method, levels = c("SimTopK", "CapsuleFilter", "PairwiseGate", "MemAct-Lite"))

trial_lines <- readLines(file.path(results_dir, "per_task_results.jsonl"), warn = FALSE)
trial <- do.call(rbind, lapply(trial_lines, function(x) {
  item <- fromJSON(x)
  data.frame(
    task_id = item$task_id,
    scenario = item$scenario,
    method = item$method,
    success = item$success,
    policy_compliant = item$policy_compliant,
    unsafe_miad = item$unsafe_miad,
    ctmir = item$ctmir,
    pvar = item$pvar,
    utir = item$utir,
    smmr = item$smmr,
    stringsAsFactors = FALSE
  )
}))
trial$any_violation <- rowSums(trial[, c("unsafe_miad", "ctmir", "pvar", "utir", "smmr")]) > 0

main_trial <- trial[trial$method %in% tradeoff_levels, ]
tradeoff <- do.call(rbind, lapply(tradeoff_levels, function(m) {
  rows <- main_trial[main_trial$method == m, ]
  n <- nrow(rows)
  k_success <- sum(rows$success)
  k_violation <- sum(rows$any_violation)
  ci_success <- wilson(k_success, n) * 100
  ci_violation <- wilson(k_violation, n) * 100
  data.frame(
    Method = m,
    Label = unname(method_labels[m]),
    TSR = 100 * mean(rows$success),
    AnyViolation = 100 * mean(rows$any_violation),
    TSR_low = ci_success[1],
    TSR_high = ci_success[2],
    Violation_low = ci_violation[1],
    Violation_high = ci_violation[2],
    stringsAsFactors = FALSE
  )
}))
tradeoff$Method <- factor(tradeoff$Method, levels = tradeoff_levels)
tradeoff$label_x <- c(74, 70, 50, 92, 68, 88)
tradeoff$label_y <- c(103, 97, 41, 103, 53, 5)
tradeoff$hjust <- rep(0.5, length(tradeoff_levels))
tradeoff$vjust <- rep(0.5, length(tradeoff_levels))

fig3 <- ggplot(tradeoff, aes(x = TSR, y = AnyViolation, colour = Method)) +
  annotate("rect", xmin = 80, xmax = 100, ymin = 0, ymax = 10, fill = "#2A8C80", alpha = 0.07) +
  geom_segment(aes(x = TSR_low, xend = TSR_high, y = AnyViolation, yend = AnyViolation), linewidth = 0.32, alpha = 0.75) +
  geom_segment(aes(x = TSR, xend = TSR, y = Violation_low, yend = Violation_high), linewidth = 0.32, alpha = 0.75) +
  geom_point(size = 2.4) +
  geom_text(aes(x = label_x, y = label_y, label = Label, hjust = hjust, vjust = vjust), size = 2.0, colour = "#20242A") +
  geom_vline(xintercept = 80, linetype = "dashed", linewidth = 0.22, colour = "#A1A8B0") +
  geom_hline(yintercept = 10, linetype = "dashed", linewidth = 0.22, colour = "#A1A8B0") +
  scale_colour_manual(values = method_palette, guide = "none") +
  scale_x_continuous(breaks = seq(40, 100, 20), expand = expansion(mult = c(0.02, 0.04))) +
  scale_y_continuous(breaks = seq(0, 100, 25), expand = expansion(mult = c(0.02, 0.04))) +
  coord_cartesian(xlim = c(40, 100), ylim = c(0, 105), clip = "off") +
  labs(
    title = "Utility--safety tradeoff",
    x = "Raw task success (TSR, %)",
    y = "Tasks with any memory-induced violation (%)"
  ) +
  theme(plot.margin = margin(4, 5, 4, 4))

scenario_long <- do.call(rbind, lapply(failure_levels, function(metric) {
  data.frame(
    Scenario = scenario$Scenario,
    Method = scenario$Method,
    Metric = metric,
    Rate = scenario[[metric]]
  )
}))
scenario_long$Metric <- factor(scenario_long$Metric, levels = failure_levels)
scenario_long$Method <- factor(scenario_long$Method, levels = method_levels)
scenario_long <- scenario_long[scenario_long$Method %in% failure_method_levels, ]
scenario_long$Method <- factor(as.character(scenario_long$Method), levels = failure_method_levels)

failure_palette <- c(
  "Unsafe MIAD" = "#C75B54",
  "CTMIR" = "#D99765",
  "PVAR" = "#7A68A6",
  "UTIR" = "#6F91B5",
  "SMMR" = "#8D99A6"
)

fig4 <- ggplot(scenario_long, aes(x = Method, y = Rate, fill = Metric)) +
  geom_col(position = position_dodge(width = 0.78), width = 0.68, linewidth = 0.12, colour = "white") +
  facet_grid(. ~ Scenario) +
  scale_x_discrete(labels = method_labels_short) +
  scale_y_continuous(breaks = seq(0, 100, 25), limits = c(0, 100), expand = expansion(mult = c(0, 0.04))) +
  scale_fill_manual(values = failure_palette) +
  guides(fill = guide_legend(nrow = 1, byrow = TRUE)) +
  labs(title = NULL, x = NULL, y = "Failure rate (%)", fill = NULL) +
  theme(
    axis.text.x = element_text(angle = 0, hjust = 0.5, size = 4.8),
    legend.position = "top",
    legend.margin = margin(-2, 0, -2, 0),
    legend.box.margin = margin(0, 0, -3, 0),
    panel.grid.major.x = element_blank(),
    plot.margin = margin(0, 3, 0, 2)
  )

ablation_methods <- c("Full MemAct", "w/o PrivacyFilter", "w/o ActionProbe", "w/o UsagePolicy", "w/o FreshnessCheck", "w/o SetRecheck")
ablation_labels <- c(
  "Full MemAct" = "Full MemAct",
  "w/o PrivacyFilter" = "w/o Privacy",
  "w/o ActionProbe" = "w/o Probe",
  "w/o UsagePolicy" = "w/o Usage",
  "w/o FreshnessCheck" = "w/o Freshness",
  "w/o SetRecheck" = "w/o Set"
)
ab_trial <- trial[trial$method %in% ablation_methods, ]
ab_summary <- do.call(rbind, lapply(ablation_methods, function(m) {
  rows <- ab_trial[ab_trial$method == m, ]
  n <- nrow(rows)
  pc <- sum(rows$success & rows$policy_compliant)
  av <- sum(rows$any_violation)
  pc_ci <- wilson(pc, n) * 100
  av_ci <- wilson(av, n) * 100
  rbind(
    data.frame(Variant = m, Metric = "PCSR", Rate = 100 * pc / n, Low = pc_ci[1], High = pc_ci[2]),
    data.frame(Variant = m, Metric = "Any violation", Rate = 100 * av / n, Low = av_ci[1], High = av_ci[2])
  )
}))
ab_summary$Variant <- factor(ab_summary$Variant, levels = rev(ablation_methods))
ab_summary$Metric <- factor(ab_summary$Metric, levels = c("PCSR", "Any violation"))

ab_summary$VariantShort <- factor(
  unname(ablation_labels[as.character(ab_summary$Variant)]),
  levels = rev(unname(ablation_labels[ablation_methods]))
)

ab_bar <- ggplot(ab_summary, aes(x = VariantShort, y = Rate, fill = Metric)) +
  geom_col(position = position_dodge(width = 0.62), width = 0.54, colour = "white", linewidth = 0.15) +
  geom_errorbar(
    aes(ymin = Low, ymax = High),
    position = position_dodge(width = 0.62),
    width = 0.11,
    linewidth = 0.16,
    colour = "#7E8790",
    alpha = 0.62
  ) +
  coord_flip() +
  scale_fill_manual(values = c("PCSR" = "#2A8C80", "Any violation" = "#C75B54")) +
  guides(fill = guide_legend(nrow = 1, byrow = TRUE)) +
  scale_y_continuous(breaks = seq(0, 100, 25), limits = c(0, 100), expand = expansion(mult = c(0, 0.03))) +
  labs(title = "Component removal", x = NULL, y = "Rate (%)", fill = NULL) +
  theme(
    legend.position = "top",
    legend.justification = "left",
    legend.margin = margin(-2, 0, -2, 0),
    legend.box.margin = margin(0, 0, -3, 0),
    axis.text.y = element_text(size = 5.2),
    plot.margin = margin(0, 3, 0, 2)
  )

line_palette <- c("SimTopK" = "#8D99A6", "CapsuleFilter" = "#6F91B5", "PairwiseGate" = "#7A68A6", "MemAct-Lite" = "#2A8C80")
line_shapes <- c("SimTopK" = 16, "CapsuleFilter" = 15, "PairwiseGate" = 17, "MemAct-Lite" = 18)
sens_pcsr <- ggplot(sensitivity, aes(x = CandidateK, y = PCSR, colour = Method, shape = Method)) +
  geom_line(linewidth = 0.42) +
  geom_point(size = 1.65, stroke = 0.35) +
  scale_colour_manual(values = line_palette, labels = method_labels_short[names(line_palette)]) +
  scale_shape_manual(values = line_shapes, labels = method_labels_short[names(line_shapes)]) +
  guides(
    colour = guide_legend(nrow = 1, byrow = TRUE),
    shape = guide_legend(nrow = 1, byrow = TRUE)
  ) +
  scale_x_continuous(breaks = sort(unique(sensitivity$CandidateK))) +
  scale_y_continuous(breaks = seq(0, 100, 25), limits = c(0, 100), expand = expansion(mult = c(0.02, 0.03))) +
  labs(title = "PCSR vs. K", x = "K", y = "PCSR (%)", colour = NULL, shape = NULL) +
  theme(
    legend.position = "top",
    legend.margin = margin(-2, 0, -2, 0),
    legend.box.margin = margin(0, 0, -3, 0),
    plot.margin = margin(0, 3, 0, 2)
  )

sens_viol <- ggplot(sensitivity, aes(x = CandidateK, y = AnyViol, colour = Method, shape = Method)) +
  geom_line(linewidth = 0.42) +
  geom_point(size = 1.65, stroke = 0.35) +
  scale_colour_manual(values = line_palette, labels = method_labels_short[names(line_palette)], guide = "none") +
  scale_shape_manual(values = line_shapes, labels = method_labels_short[names(line_shapes)], guide = "none") +
  scale_x_continuous(breaks = sort(unique(sensitivity$CandidateK))) +
  scale_y_continuous(breaks = seq(0, 100, 25), limits = c(0, 100), expand = expansion(mult = c(0.02, 0.03))) +
  labs(title = "AnyViol vs. K", x = "K", y = "Any violation (%)") +
  theme(
    panel.grid.major.x = element_line(linewidth = 0.15, colour = "#EEF0F2"),
    plot.margin = margin(0, 3, 0, 2)
  )

fig5 <- ab_bar + sens_pcsr + sens_viol + plot_layout(widths = c(0.95, 1.05, 1.05)) +
  plot_annotation(tag_levels = "A") &
  theme(plot.tag = element_text(size = 6.5, face = "bold"))

save_pub_r(fig4, "fig4_memoryact_failure_breakdown", width_mm = 183, height_mm = 52)
save_pub_r(fig5, "fig5_memoryact_ablation", width_mm = 183, height_mm = 54)

qa <- data.frame(
  figure = c("fig4_memoryact_failure_breakdown", "fig5_memoryact_ablation"),
  backend = "R",
  source_data = c(
    "table_iii_scenario_results.csv",
    "per_task_results.jsonl; table_iv_ablation.csv; table_vi_candidate_sensitivity.csv; table_vii_probe_sensitivity.csv; table_viii_stress_results.csv; table_ix_clean_utility.csv; table_x_trace_cases.csv"
  ),
  export = "SVG, PDF, TIFF"
)
write.csv(qa, file.path(figure_dir, "figure_qa_notes.csv"), row.names = FALSE)
