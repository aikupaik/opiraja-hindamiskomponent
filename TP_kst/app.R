# =============================================================================
# TP (Testipleier) - Shiny UI
#
# Kasutus: embed'itakse OR veebiäppi iframe'ina, URL kujul
#   .../TP_app/?test_id=<uuid>
# =============================================================================

library(shiny)
source("TP_loogika.R")

ui <- fluidPage(
  tags$head(tags$style(HTML("
    body { font-family: -apple-system, sans-serif; }
    .juhis { font-weight: 500; color: #5F5E5A; margin-bottom: 4px; }
    .tyvi { font-size: 18px; margin-bottom: 12px; }
    .stiimul { background: #F1EFE8; border-radius: 8px; padding: 12px; margin-bottom: 16px; }
    .valik-plokk {
      padding: 14px 16px; margin: 8px 0; border: 2px solid #D3D1C7; border-radius: 10px;
      cursor: pointer; font-size: 16px; transition: all 0.15s;
    }
    .valik-plokk:hover { border-color: #888780; }
    .valik-plokk.valitud { border-color: #0F6E56; background: #E1F5EE; font-weight: 500; }
    .edasi-nupp { margin-top: 20px; width: 100%; padding: 14px; font-size: 16px; }
    .lopp-teade { text-align: center; padding: 60px 20px; font-size: 20px; }
    .tagasiside-kokkuvote { font-size: 19px; font-weight: 600; margin-bottom: 20px; text-align: center; color: #0F6E56; }
    .tagasiside-plokk { margin-bottom: 22px; }
    .tagasiside-plokk h4 { font-size: 15px; color: #5F5E5A; margin-bottom: 8px; }
    .tagasiside-sildid { list-style: none; padding: 0; margin: 0; }
    .tagasiside-sildid li {
      display: inline-block; padding: 6px 12px; margin: 3px 4px 3px 0;
      border-radius: 16px; font-size: 14px;
    }
    .silt-omandatud { background: #E1F5EE; color: #0F6E56; }
    .silt-valmis { background: #FEF3D7; color: #8A6300; }
    .silt-korda { background: #FBE4E1; color: #9B3B2E; }
    .tagasiside-markus { font-size: 13px; color: #8A897E; margin-top: 6px; }
    .tagasiside-turvapiir { font-size: 13px; background: #F1EFE8; padding: 10px 12px; border-radius: 8px; margin-top: 16px; }
    .tagasiside-roosa    { background: #FBE4E1; color: #7A2E22; }
    .tagasiside-kollane  { background: #FEF3D7; color: #8A6300; }
    .tagasiside-roheline { background: #E1F5EE; color: #0F6E56; }
  "))),
  div(style = "max-width: 480px; margin: 0 auto; padding: 20px;",
      uiOutput("sisu"))
)

server <- function(input, output, session) {
  
  test_id_val <- reactive({
    query <- parseQueryString(session$clientData$url_search)
    query$test_id
  })
  
  seisund <- reactiveValues(
    laetud = FALSE,
    andmed = NULL,
    praegune = NULL,
    valitud_vastus = NULL,
    lopetatud = FALSE,
    tulemus_naidatud = FALSE,
    tulemuste_leht = FALSE,
    lopp_profiil = NULL,
    viga = NULL,
    progressi_tekst = "Testi kavandatakse..."
  )
  
  # Ehitab kasutajale kuvatava tulemuste lehe lopeta_test() väljundist.
  # Kolm rubriiki näidatakse alati (ka tühjadena), et struktuur oleks ühtlane
  # sõltumata sellest, mida OR selle testi jaoks tellis.
  tagasiside_ui <- function(lp) {
    if (is.null(lp)) {
      return(div(class = "lopp-teade", "Tagasiside pole hetkel kättesaadav."))
    }
    voiks_oppida <- c(lp$valmis_oppima, lp$ebamaarane_edasi)
    tasuks_korrata <- lp$ebamaarane_tagasi
    tagList(
      if (!is.null(lp$kokkuvote)) div(class = "tagasiside-kokkuvote", lp$kokkuvote),
      div(
        class = "tagasiside-plokk",
        h4("Juba oskad:"),
        if (length(lp$omandatud) > 0) {
          tags$ul(class = "tagasiside-sildid",
                  lapply(lp$omandatud, function(s) tags$li(class = "silt-omandatud", s)))
        } else {
          div(class = "tagasiside-markus", "Sellest testist ei leidnud me veel midagi kindlalt kinnitatut.")
        }
      ),
      div(
        class = "tagasiside-plokk",
        h4("Võid õppida / rohkem süveneda:"),
        if (length(voiks_oppida) > 0) {
          tags$ul(class = "tagasiside-sildid",
                  lapply(voiks_oppida, function(s) tags$li(class = "silt-valmis", s)))
        } else {
          div(class = "tagasiside-markus", "Vastused ei  pole uut suunda pakkuda.")
        }
      ),
      div(
        class = "tagasiside-plokk",
        h4("Tasuks korrata:"),
        if (length(tasuks_korrata) > 0) {
          tags$ul(class = "tagasiside-sildid",
                  lapply(tasuks_korrata, function(s) tags$li(class = "silt-korda", s)))
        } else {
          div(class = "tagasiside-markus", "Midagi kindlat kordamist ei vaja.")
        }
      ),
      if (identical(lp$peatumise_pohjus, "turvapiir")) {
        pct <- round(lp$kindlus_parim_olek * 100)
        varv <- if (pct <= 49) "tagasiside-roosa" else if (pct <= 79) "tagasiside-kollane" else "tagasiside-roheline"
        div(class = paste("tagasiside-turvapiir", varv),
            sprintf("Test määras Sinu teadmiste profiili %d%% tõenäosuse tasemel.", pct))
      }
    )
  }
  
  # Valib järgmise sõlme (half-split) ja selle sõlme jaoks konkreetse ülesande.
  vali_jargmine_kusimus <- function(andmed) {
    samm <- function(silt, avaldis) {
      tryCatch(avaldis, error = function(e) {
        stop(sprintf("[%s] %s", silt, conditionMessage(e)), call. = FALSE)
      })
    }
    solm_indeks <- samm("vali_jargmine_solm", vali_jargmine_solm(andmed$posterior, andmed$K))
    solm <- samm("solm_indeks->solmed", andmed$solmed[solm_indeks])
    kysitud_yp_idd <- samm("kysitud_yp_idd", {
      if (length(andmed$kysitud) == 0) integer(0)
      else sapply(andmed$kysitud, function(k) k$yp_id)
    })
    item <- samm("vali_ylesanne_solmele", vali_ylesanne_solmele(solm, kysitud_yp_idd))
    ylesanne <- samm("lae_ylesanne", lae_ylesanne(item$yp_id))
    list(solm_indeks = solm_indeks, solm = solm, item = item, ylesanne = ylesanne)
  }
  
  # Testi laadimine URL-i test_id järgi - kontrollib kohe, kas test on juba
  # aktiivne, muidu jääb poll-tsükkel (allpool) seda ootama.
  observeEvent(test_id_val(), {
    req(test_id_val())
    tryCatch({
      vastus <- kysi_ata_edenemist(test_id_val())
      if (!is.null(vastus$viga)) stop(vastus$viga)
      if (isTRUE(vastus$edenemine$test_aktiivne)) {
        andmed <- lae_tp_seisund(test_id_val())
        seisund$andmed <- andmed
        seisund$praegune <- vali_jargmine_kusimus(andmed)
        seisund$laetud <- TRUE
      } else {
        pt <- progressi_tekst(vastus)
        if (identical(pt, "VIGA")) {
          seisund$viga <- "Ülesannete koostamine ebaõnnestus (YG/AI teenus tagastas vea). Palun proovi mõne aja pärast uuesti, või anna sellest õpetajale/administraatorile teada."
        } else {
          seisund$progressi_tekst <- pt
        }
      }
    }, error = function(e) {
      seisund$viga <- conditionMessage(e)
    })
  })
  
  # Kordab ATA staatuse küsimist iga 3s, kuni test läheb aktiivseks - see
  # päring ise käivitab ATA rada 6, kui YP katvus on vahepeal täis saanud.
  observe({
    req(!seisund$laetud, is.null(seisund$viga), test_id_val())
    invalidateLater(3000, session)
    isolate({
      tryCatch({
        vastus <- kysi_ata_edenemist(test_id_val())
        if (!is.null(vastus$viga)) {
          seisund$viga <- vastus$viga
        } else if (isTRUE(vastus$edenemine$test_aktiivne)) {
          andmed <- lae_tp_seisund(test_id_val())
          seisund$andmed <- andmed
          seisund$praegune <- vali_jargmine_kusimus(andmed)
          seisund$laetud <- TRUE
        } else {
          pt <- progressi_tekst(vastus)
          if (identical(pt, "VIGA")) {
            seisund$viga <- "Ülesannete koostamine ebaõnnestus (YG/AI teenus tagastas vea). Palun proovi mõne aja pärast uuesti, või anna sellest õpetajale/administraatorile teada."
          } else {
            seisund$progressi_tekst <- pt
          }
        }
      }, error = function(e) {
        seisund$viga <- conditionMessage(e)
      })
    })
  })
  
  # Peamine kuva - vastavalt olekule kas viga, ootamine, küsimus või tulemus.
  output$sisu <- renderUI({
    if (!is.null(seisund$viga)) {
      return(div(class = "lopp-teade", p(strong("Viga:")), p(seisund$viga)))
    }
    if (!seisund$laetud) {
      return(div(class = "lopp-teade", seisund$progressi_tekst))
    }
    if (seisund$tulemuste_leht) {
      return(tagasiside_ui(seisund$lopp_profiil))
    }
    if (seisund$tulemus_naidatud) {
      return(div(class = "lopp-teade",
                 p("Test on läbi."),
                 actionButton("vaata_tulemust", "Tulemused", class = "edasi-nupp")))
    }
    if (seisund$lopetatud) {
      return(div(class = "lopp-teade", "Aitäh! Test on läbi."))
    }
    
    yl <- seisund$praegune$ylesanne
    tagList(
      div(class = "juhis", yl$juhis),
      div(class = "tyvi", yl$tyvi),
      if (!is.null(yl$stiimul)) div(class = "stiimul", yl$stiimul),
      lapply(seq_along(yl$variandid), function(i) {
        v <- yl$variandid[i]
        valitud <- identical(seisund$valitud_vastus, v)
        tags$div(
          class = paste("valik-plokk", if (valitud) "valitud" else ""),
          onclick = sprintf(
            "Shiny.setInputValue('valik_klikk', %s, {priority: 'event'})",
            jsonlite::toJSON(list(vastus = v, aeg = as.numeric(Sys.time())), auto_unbox = TRUE)
          ),
          v
        )
      }),
      actionButton("edasi_btn", "Edasi", class = "edasi-nupp")
    )
  })
  
  observeEvent(input$valik_klikk, {
    seisund$valitud_vastus <- input$valik_klikk$vastus
  })
  
  # Vastuse salvestamine, posterior'i uuendamine ja peatumiskontroll.
  observeEvent(input$edasi_btn, {
    req(seisund$valitud_vastus)
    andmed <- seisund$andmed
    praegune <- seisund$praegune
    
    vastus_oige <- identical(seisund$valitud_vastus, praegune$ylesanne$voti)
    
    tryCatch({
      sb_post("/tulemustepank", list(
        test_id = andmed$test_id,
        yp_id = praegune$item$yp_id,
        skoor = as.integer(vastus_oige),
        valitud_vastus = seisund$valitud_vastus
      ))
      
      sb_patch(sprintf("/ylesandepank?yp_id=eq.%s", praegune$item$yp_id), list(
        kasutamiste_arv = praegune$item$kasutamiste_arv + 1,
        viimane_kasutus = as.character(Sys.time())
      ))
      
      uus_posterior <- uuenda_posterior(
        andmed$posterior, andmed$K, praegune$solm_indeks, vastus_oige,
        andmed$testi_loogika$beta, andmed$testi_loogika$eta
      )
      uus_kysitud <- c(andmed$kysitud, list(list(
        yp_id = praegune$item$yp_id, solm = praegune$solm, vastus_oige = vastus_oige
      )))
      
      salvesta_tp_seisund(andmed$test_id, uus_posterior, uus_kysitud)
      
      # Peatumisreeglid: reliaabluse_pohi = miinimum vaatlusi, turvapiir =
      # maksimum vaatlusi; loomulik peatumine nõuab MÕLEMAT (kindlust JA
      # miinimumi täitumist).
      reliaabluse_pohi <- function(n) min(max(7, ceiling(1.5 * n)), 10)
      turvapiir <- function(n) max(2 * n, reliaabluse_pohi(n) + 1)
      n_solme <- length(andmed$solmed)
      
      # Kindluse lävi 0.9 (tõstetud 0.8-lt 01.08.2026 - simulatsioonid
      # näitasid selget täpsuse paranemist "õnneliku"/äraarvava vastamisviisi
      # korral, samas kui hoolika vastaja jaoks jääb tulemus endiselt kiire).
      loomulik_valmis <- max(uus_posterior) >= 0.9 && length(uus_kysitud) >= reliaabluse_pohi(n_solme)
      if (loomulik_valmis || length(uus_kysitud) >= turvapiir(n_solme)) {
        peatumise_pohjus <- if (loomulik_valmis) "loomulik" else "turvapiir"
        seisund$lopp_profiil <- lopeta_test(
          andmed$test_id, uus_posterior, andmed$solmed, andmed$K, peatumise_pohjus
        )
        seisund$lopetatud <- TRUE
        seisund$viga <- NULL
      } else {
        andmed$posterior <- uus_posterior
        andmed$kysitud <- uus_kysitud
        seisund$andmed <- andmed
        seisund$praegune <- vali_jargmine_kusimus(andmed)
        seisund$valitud_vastus <- NULL
      }
    }, error = function(e) {
      seisund$viga <- conditionMessage(e)
    })
  })
  
  observe({
    req(seisund$lopetatud, !seisund$tulemus_naidatud)
    invalidateLater(1500, session)
    isolate({ seisund$tulemus_naidatud <- TRUE })
  })
  
  observeEvent(input$vaata_tulemust, {
    seisund$tulemuste_leht <- TRUE
  })
}

shinyApp(ui, server)
