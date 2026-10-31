#!/usr/bin/env Rscript
# mediation.R -- Kenny-Judd lagged SEM via lavaan bootstrap.
#
# Reads a JSON payload from stdin:
#   { data_input, seed }
# Writes a JSON object to stdout:
#   { paths, fit }
#
# Requires: lavaan, jsonlite.
suppressMessages({
  library(lavaan)
  library(jsonlite)
})

payload <- fromJSON(paste(readLines(file("stdin"), warn = FALSE), collapse = "\n"))
set.seed(as.integer(payload$seed))

df <- read.csv(payload$data_input, stringsAsFactors = FALSE)

model_spec <- '
  pain_t ~ a * pain_t_minus_1
  willingness_t ~ b * pain_t + c * willingness_t_minus_1
  indirect := a * b
  total := c + a * b
'

fit <- sem(model_spec, data = df, se = "bootstrap", bootstrap = 5000)
params <- parameterEstimates(fit, boot.ci.type = "bca.simple")

out <- list(
  paths = as.data.frame(params),
  fit = fitMeasures(fit, c("cfi", "rmsea", "srmr"))
)

cat(toJSON(out, auto_unbox = TRUE, pretty = TRUE))
