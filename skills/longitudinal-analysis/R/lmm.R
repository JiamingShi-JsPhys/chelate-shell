#!/usr/bin/env Rscript
# lmm.R -- fit a linear mixed model and emit JSON for the Python pipeline.
#
# Reads a JSON payload from stdin:
#   { data_input, formula, reml, seed }
# Writes a JSON object to stdout:
#   { fixed_effects, marginal_means, aic, bic, n }
#
# Requires: lme4, emmeans, jsonlite, data.table (or base::read.csv).
suppressMessages({
  library(lme4)
  library(emmeans)
  library(jsonlite)
})

payload <- fromJSON(paste(readLines(file("stdin"), warn = FALSE), collapse = "\n"))
set.seed(as.integer(payload$seed))

df <- read.csv(payload$data_input, stringsAsFactors = FALSE)

formula <- as.formula(payload$formula)
model <- lmer(formula, data = df, REML = isTRUE(payload$reml))

fixed <- as.data.frame(summary(model)$coefficients)
marginal <- tryCatch(
  as.data.frame(emmeans(model, ~ session | default)),
  error = function(e) NULL
)

out <- list(
  fixed_effects = fixed,
  marginal_means = marginal,
  aic = AIC(model),
  bic = BIC(model),
  n = nobs(model)
)

cat(toJSON(out, auto_unbox = TRUE, pretty = TRUE))
