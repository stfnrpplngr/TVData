# Client-side compatible Shiny app for salary table comparison.
# Assumption: All input files are repository-local and loaded via relative paths.

library(shiny)

read_optional_csv <- function(path, required_cols = NULL) {
  if (!file.exists(path)) return(NULL)

  dat <- tryCatch(
    read.csv(path, stringsAsFactors = FALSE),
    error = function(e) NULL
  )

  if (is.null(dat)) return(NULL)
  if (!is.null(required_cols) && !all(required_cols %in% names(dat))) return(NULL)
  dat
}

fallback_data <- function() {
  tables <- data.frame(
    tariff_id = rep(c("TV-L", "TVöD-VKA"), each = 6),
    pay_group = rep("E9", 12),
    step = rep(1:6, 2),
    amount_monthly = c(3600, 3800, 4000, 4200, 4400, 4600, 3500, 3700, 3920, 4150, 4380, 4610),
    stringsAsFactors = FALSE
  )

  components <- data.frame(
    tariff_id = c("TV-L", "TV-L", "TV-L", "TV-L", "TVöD-VKA", "TVöD-VKA", "TVöD-VKA", "TVöD-VKA"),
    component = rep(c("Jahressonderzahlung", "VWL", "Zulagen", "Grundentgelt"), 2),
    amount_monthly = c(220, 6.65, 80, 0, 180, 6.65, 65, 0),
    percent = NA_real_,
    scope_pay_group = NA_character_,
    stringsAsFactors = FALSE
  )

  meta <- data.frame(
    tariff_id = c("TV-L", "TVöD-VKA"),
    valid_from = c("2025-01-01", "2025-01-01"),
    source_url = c("https://example.org/tv-l", "https://example.org/tvoed-vka"),
    notes = c("Demo fallback", "Demo fallback"),
    license_note = c("CC BY 4.0 (demo)", "CC BY 4.0 (demo)"),
    version = c("demo-1", "demo-1"),
    stringsAsFactors = FALSE
  )

  list(tables = tables, components = components, meta = meta)
}

load_data <- function() {
  tables <- read_optional_csv(
    "data/tables.csv",
    c("tariff_id", "pay_group", "step", "amount_monthly")
  )

  components <- read_optional_csv(
    "data/components.csv",
    c("tariff_id", "component")
  )

  meta <- read_optional_csv(
    "data/meta.csv",
    c("tariff_id", "valid_from", "source_url", "notes", "license_note")
  )

  if (is.null(tables) || nrow(tables) == 0) {
    return(fallback_data())
  }

  if (is.null(components) || nrow(components) == 0) {
    components <- fallback_data()$components
  }

  if (is.null(meta) || nrow(meta) == 0) {
    meta <- fallback_data()$meta
  }

  if (!"amount_monthly" %in% names(components)) components$amount_monthly <- NA_real_
  if (!"percent" %in% names(components)) components$percent <- NA_real_
  if (!"scope_pay_group" %in% names(components)) components$scope_pay_group <- NA_character_
  if (!"version" %in% names(meta)) meta$version <- "n/a"

  tables$step <- suppressWarnings(as.numeric(tables$step))
  tables$amount_monthly <- suppressWarnings(as.numeric(tables$amount_monthly))
  components$amount_monthly <- suppressWarnings(as.numeric(components$amount_monthly))
  components$percent <- suppressWarnings(as.numeric(components$percent))

  list(tables = tables, components = components, meta = meta)
}

calc_component_addition <- function(base_amounts, tariff, pay_group, selected_components, components_df) {
  if (!length(selected_components)) return(rep(0, length(base_amounts)))

  rows <- components_df[
    components_df$tariff_id == tariff & components_df$component %in% selected_components,
    ,
    drop = FALSE
  ]

  if (nrow(rows) == 0) return(rep(0, length(base_amounts)))

  scoped <- is.na(rows$scope_pay_group) | rows$scope_pay_group == "" | rows$scope_pay_group == pay_group
  rows <- rows[scoped, , drop = FALSE]
  if (nrow(rows) == 0) return(rep(0, length(base_amounts)))

  abs_add <- sum(rows$amount_monthly, na.rm = TRUE)
  pct_add <- sum(rows$percent, na.rm = TRUE) / 100

  abs_add + base_amounts * pct_add
}

ui <- fluidPage(
  titlePanel("Entgelttabellen-Vergleich (Shinylive, clientseitig)"),
  sidebarLayout(
    sidebarPanel(
      selectInput("tariff_a", "Tarif A", choices = NULL),
      selectInput("tariff_b", "Tarif B", choices = NULL),
      checkboxGroupInput(
        "components",
        "Komponenten",
        choices = c("Grundentgelt", "Jahressonderzahlung", "VWL", "Zulagen"),
        selected = c("Grundentgelt")
      ),
      selectInput("pay_group", "Entgeltgruppe", choices = NULL),
      sliderInput("step_range", "Stufe Bereich", min = 1, max = 6, value = c(1, 6), step = 1)
    ),
    mainPanel(
      h4("Vergleich je Stufe"),
      tableOutput("comparison_table"),
      h4("Linienchart"),
      plotOutput("line_plot", height = "280px"),
      h4("Heatmap (Differenz A - B)"),
      plotOutput("heatmap_plot", height = "300px"),
      h4("Quellen"),
      tableOutput("sources")
    )
  )
)

server <- function(input, output, session) {
  dat <- load_data()

  tariffs <- sort(unique(dat$tables$tariff_id))
  updateSelectInput(session, "tariff_a", choices = tariffs, selected = tariffs[1])
  updateSelectInput(session, "tariff_b", choices = tariffs, selected = tariffs[min(2, length(tariffs))])

  observe({
    req(input$tariff_a, input$tariff_b)
    pg <- sort(unique(dat$tables$pay_group[dat$tables$tariff_id %in% c(input$tariff_a, input$tariff_b)]))
    updateSelectInput(session, "pay_group", choices = pg, selected = pg[1])
  })

  observe({
    req(input$pay_group)
    st <- dat$tables$step[dat$tables$pay_group == input$pay_group]
    st <- st[is.finite(st)]
    if (length(st) > 0) {
      updateSliderInput(session, "step_range", min = min(st), max = max(st), value = c(min(st), max(st)))
    }
  })

  compare_df <- reactive({
    req(input$tariff_a, input$tariff_b, input$pay_group, input$step_range)

    table_a <- dat$tables[
      dat$tables$tariff_id == input$tariff_a & dat$tables$pay_group == input$pay_group,
      c("step", "amount_monthly"),
      drop = FALSE
    ]

    table_b <- dat$tables[
      dat$tables$tariff_id == input$tariff_b & dat$tables$pay_group == input$pay_group,
      c("step", "amount_monthly"),
      drop = FALSE
    ]

    names(table_a)[2] <- "amount_a"
    names(table_b)[2] <- "amount_b"

    merged <- merge(table_a, table_b, by = "step", all = FALSE)
    merged <- merged[order(merged$step), , drop = FALSE]
    merged <- merged[merged$step >= input$step_range[1] & merged$step <= input$step_range[2], , drop = FALSE]

    if (nrow(merged) == 0) return(merged)

    with_base_a <- "Grundentgelt" %in% input$components
    with_base_b <- "Grundentgelt" %in% input$components

    base_a <- if (with_base_a) merged$amount_a else rep(0, nrow(merged))
    base_b <- if (with_base_b) merged$amount_b else rep(0, nrow(merged))

    add_a <- calc_component_addition(base_a, input$tariff_a, input$pay_group, setdiff(input$components, "Grundentgelt"), dat$components)
    add_b <- calc_component_addition(base_b, input$tariff_b, input$pay_group, setdiff(input$components, "Grundentgelt"), dat$components)

    merged$betrag_a <- round(base_a + add_a, 2)
    merged$betrag_b <- round(base_b + add_b, 2)
    merged$differenz_abs <- round(merged$betrag_a - merged$betrag_b, 2)
    merged$differenz_rel <- ifelse(merged$betrag_b == 0, NA_real_, round((merged$differenz_abs / merged$betrag_b) * 100, 2))

    merged
  })

  output$comparison_table <- renderTable({
    df <- compare_df()
    validate(need(nrow(df) > 0, "Keine vergleichbaren Daten für die gewählten Filter."))
    out <- df[, c("step", "betrag_a", "betrag_b", "differenz_abs", "differenz_rel")]
    names(out) <- c("Stufe", "Betrag A", "Betrag B", "Differenz absolut", "Differenz relativ (%)")
    out
  }, striped = TRUE, bordered = TRUE, digits = 2)

  output$line_plot <- renderPlot({
    df <- compare_df()
    validate(need(nrow(df) > 0, "Keine Daten für Plot."))
    ylim <- range(c(df$betrag_a, df$betrag_b), na.rm = TRUE)
    plot(df$step, df$betrag_a, type = "o", col = "#1f77b4", pch = 16, lwd = 2,
         xlab = "Stufe", ylab = "Betrag (monatlich)", ylim = ylim)
    lines(df$step, df$betrag_b, type = "o", col = "#d62728", pch = 17, lwd = 2)
    legend("topleft", legend = c(input$tariff_a, input$tariff_b), col = c("#1f77b4", "#d62728"),
           pch = c(16, 17), lwd = 2, bty = "n")
  })

  output$heatmap_plot <- renderPlot({
    req(input$tariff_a, input$tariff_b)
    rows <- dat$tables[dat$tables$tariff_id %in% c(input$tariff_a, input$tariff_b), , drop = FALSE]
    groups <- sort(unique(rows$pay_group))
    steps <- sort(unique(rows$step))

    mat <- matrix(NA_real_, nrow = length(groups), ncol = length(steps), dimnames = list(groups, steps))

    for (g in groups) {
      for (s in steps) {
        a <- rows$amount_monthly[rows$tariff_id == input$tariff_a & rows$pay_group == g & rows$step == s]
        b <- rows$amount_monthly[rows$tariff_id == input$tariff_b & rows$pay_group == g & rows$step == s]
        if (length(a) && length(b)) {
          mat[as.character(g), as.character(s)] <- a[1] - b[1]
        }
      }
    }

    validate(need(any(is.finite(mat)), "Keine Heatmap-Daten verfügbar."))

    filled <- mat
    filled[is.na(filled)] <- 0
    image(
      x = seq_len(ncol(filled)),
      y = seq_len(nrow(filled)),
      z = t(filled),
      col = colorRampPalette(c("#2166ac", "#f7f7f7", "#b2182b"))(100),
      axes = FALSE,
      xlab = "Stufe",
      ylab = "Entgeltgruppe"
    )
    axis(1, at = seq_len(ncol(filled)), labels = colnames(filled))
    axis(2, at = seq_len(nrow(filled)), labels = rownames(filled), las = 2)
    box()
  })

  output$sources <- renderTable({
    req(input$tariff_a, input$tariff_b)
    src <- dat$meta[dat$meta$tariff_id %in% c(input$tariff_a, input$tariff_b), , drop = FALSE]
    if (!"version" %in% names(src)) src$version <- "n/a"
    src[, c("tariff_id", "valid_from", "source_url", "version", "notes", "license_note"), drop = FALSE]
  }, striped = TRUE, bordered = TRUE)
}

shinyApp(ui, server)
