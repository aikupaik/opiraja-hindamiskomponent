# =============================================================================
# TP (Testipleier) - Shiny UI
#
# Kasutus: embed'itakse OR veebiäppi iframe'ina, URL kujul
#   .../TP_app/?test_id=<uuid>
#
# NB: TP_loogika.R sisaldab kmassesshalfsplit()/kmassessbayesian() kutseid,
# mis vajavad kohapealset kinnitust enne usaldamist (vt hoiatus seal failis).
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
    andmed = NULL,        # lae_tp_seisund() väljund
    praegune = NULL,       # praegune ülesanne (solm_indeks, item, ylesanne)
    valitud_vastus = NULL,
    lopetatud = FALSE,
    tulemus_naidatud = FALSE,
    tulemuste_leht = FALSE,   # 17.07.2026 - kas kasutaja on "Tulemused" nupule vajutanud
    lopp_profiil = NULL,   # lopeta_test() tagastatud tagasiside (17.07.2026)
    viga = NULL,
    progressi_tekst = "Testi kavandatakse..."
  )
  
  # Ehitab "Tulemused" lehe lopeta_test() väljundi (lopp_profiil) põhjal.
  # NB: 19.07.2026 - vt vestlus demo eel ("hea kui inimesed teavad, mida
  # oodata"). Kolm rubriiki näidatakse ALATI (fikseeritud pealkirjadega,
  # ka siis kui nimekiri on tühi) - kasutaja/vaataja ei tea, mis täpselt
  # OR selle testi jaoks tellis, nii et ühtlane struktuur on olulisem kui
  # tühjade sektsioonide peitmine:
  #   (a) Juba oskad          <- omandatud
  #   (b) Võid õppida/süveneda <- valmis_oppima + ebamaarane_edasi
  #       (ebamäärasus siin on JULGUSTAV signaal - andmed napid, aga
  #       struktuur ütleb, et see on loogiline järgmine samm)
  #   (c) Tasuks korrata       <- ebamaarane_tagasi
  #       (ebamäärasus siin on ÜLLATAV signaal - eeldus millelegi juba
  #       kindlalt omandatule, väärib täpsemat kordustestimist)
  # "veel_mitte" (kaugemad, struktuuriliselt pole veel aktuaalsed) jääb
  # endiselt kuvamata - pole ühelegi rubriigile sisuline lisa.
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
          div(class = "tagasiside-markus", "Hetkel pole uut suunda pakkuda.")
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
      if (identical(lp$peatumise_pohjus, "turvapiir")) div(
        class = "tagasiside-turvapiir",
        "See test ei suutnud sinu teadmisi antud teemal piisavalt kindlalt eristada. Soovitatav on hiljem uuesti testida."
      )
    )
  }
  
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
  
  observeEvent(test_id_val(), {
    req(test_id_val())
    # Esmalt kontrollime kohe (mitte ootame esimest invalidateLater tsüklit) -
    # kui test on juba aktiivne (nt YP oli ammu täis), näeme seda otsekohe.
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
  
  # Kordame ATA staatuse küsimist iga 3s, kuni test läheb aktiivseks. See
  # PÄRING ISE käivitab rada 6, kui YP katvus on vahepeal täielikuks saanud -
  # pole passiivne ootamine, vaid aktiivne "torkamine".
  observe({
    req(!seisund$laetud, is.null(seisund$viga), test_id_val())
    message(sprintf("[%s] POLL-TSUKKEL kaivitus (laetud=%s, viga=%s)",
                    Sys.time(), seisund$laetud, is.null(seisund$viga)))
    invalidateLater(3000, session)
    isolate({
      tryCatch({
        vastus <- kysi_ata_edenemist(test_id_val())
        if (!is.null(vastus$viga)) {
          message(sprintf("[%s] POLL: vastus$viga = %s", Sys.time(), vastus$viga))
          seisund$viga <- vastus$viga
        } else if (isTRUE(vastus$edenemine$test_aktiivne)) {
          message(sprintf("[%s] POLL: test_aktiivne=TRUE, laadin tp_seisund", Sys.time()))
          andmed <- lae_tp_seisund(test_id_val())
          seisund$andmed <- andmed
          seisund$praegune <- vali_jargmine_kusimus(andmed)
          seisund$laetud <- TRUE
        } else {
          pt <- progressi_tekst(vastus)
          message(sprintf("[%s] POLL: veel mitte aktiivne, progressi_tekst=%s", Sys.time(), pt))
          if (identical(pt, "VIGA")) {
            seisund$viga <- "Ülesannete koostamine ebaõnnestus (YG/AI teenus tagastas vea). Palun proovi mõne aja pärast uuesti, või anna sellest õpetajale/administraatorile teada."
          } else {
            seisund$progressi_tekst <- pt
          }
        }
      }, error = function(e) {
        message(sprintf("[%s] POLL: TRYCATCH VIGA: %s", Sys.time(), conditionMessage(e)))
        seisund$viga <- conditionMessage(e)
      })
    })
  })
  
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
  
  observeEvent(input$edasi_btn, {
    req(seisund$valitud_vastus)
    andmed <- seisund$andmed
    praegune <- seisund$praegune
    
    vastus_oige <- identical(seisund$valitud_vastus, praegune$ylesanne$voti)
    
    tryCatch({
      # 1. Salvesta vastus tulemustepank
      sb_post("/tulemustepank", list(
        test_id = andmed$test_id,
        yp_id = praegune$item$yp_id,
        skoor = as.integer(vastus_oige),
        valitud_vastus = seisund$valitud_vastus
      ))
      
      # 2. Uuenda ylesandepank kasutuse loendurit (PostgREST ei toeta "+1"
      # otse PATCH kehas, seega kasutame juba päritud praegust väärtust).
      sb_patch(sprintf("/ylesandepank?yp_id=eq.%s", praegune$item$yp_id), list(
        kasutamiste_arv = praegune$item$kasutamiste_arv + 1,
        viimane_kasutus = as.character(Sys.time())
      ))
      
      # 3. Bayes-uuendus
      # NB: PARANDATUD 17.07.2026 - kmassessbayesian() ootab beta/eta
      # TÄISVEKTORITENA üle kõigi sõlmede (vastavuses K veergudega,
      # kinnitatud kutsekuju 14.07.2026), mitte konkreetse valitud
      # YP-ülesande enda skalaarseid parameetreid (item$beta/item$eta,
      # mis on üksuse-tasandi väärtused, mõeldud hilisemaks kalibreerimiseks,
      # mitte siinseks jooksvaks Bayes-uuenduseks). Varasem
      # "praegune$item$beta, praegune$item$eta" andis skalaari pikkusega 1,
      # kus funktsioon ootas sõlmede-arvu-pikkust vektorit - sellest tuli
      # "beta and pks do not fit in size". Õige allikas on mudeli tasandi
      # vektorid, mille ATA juba koostas testi_loogika sees.
      uus_posterior <- uuenda_posterior(
        andmed$posterior, andmed$K, praegune$solm_indeks, vastus_oige,
        andmed$testi_loogika$beta, andmed$testi_loogika$eta
      )
      uus_kysitud <- c(andmed$kysitud, list(list(
        yp_id = praegune$item$yp_id, solm = praegune$solm, vastus_oige = vastus_oige
      )))
      
      salvesta_tp_seisund(andmed$test_id, uus_posterior, uus_kysitud)
      
      # 4. Peatumiskontroll
      # NB: 17.07.2026 - eristame, KUMB tingimus rakendus (loomulik kindluse
      # saavutamine vs turvapiiri täitumine) - see läheb otse tagasiside
      # ausa metatasandi märkena lopp_profiil'i (vt TP_loogika.R lopeta_test()).
      #
      # NB: PARANDATUD 19.07.2026 (vestlus "reliaablus vs adaptiivsus") -
      # eilne per-sõlme katvusnõue ("iga sõlm >=2 korda") oli valesti
      # sihitud: see sundis vaatlema ka kohti, kus struktuur juba tuletab
      # teadmise (nt A-sõlme näide, kus otsest küsimust polnudki vaja) -
      # otseses vastuolus adaptiivse KST testimise mõttega ("jäta säästlikult
      # vahele, kus struktuur juba usaldusväärselt teab"). Tegelik probleem
      # ("pendeldamine") on madal ÜLDINE reliaablus (liiga vähe vaatlusi
      # KOKKU), mitte ebaühtlane jaotus sõlmede vahel - ambivalentsete
      # sõlmede kordamise eest hoolitseb niigi juba half-split ise (vt 19.07
      # neuroloogia näide, kus vale vastuse saanud sõlme küsiti automaatselt
      # uuesti). Nõue on nüüd puhtalt KOGU testi vaatluste arvu peal:
      #   reliaabluse_pohi(n) = min(max(7, ceiling(1.5*n)), 10) - kasvab
      #     väikestel graafidel, платoo'ub 10 juures (n>=7), et suuremate
      #     graafide puhul kaoks mõju peaaegu olematuks ja tavaline
      #     0.8-kindluse adaptiivne peatumine saaks jälle vabalt, säästlikult
      #     domineerida - täpselt see, mida kasutaja soovis.
      #   turvapiir(n) = max(2*n, reliaabluse_pohi(n)+1) - tagab, et floor
      #     jääb ALATI katuse alla (varasem 2*n katus n=3 puhul (6) oleks
      #     jäänud floor'ist (7) madalamaks, matemaatiliselt vastuoluline).
      reliaabluse_pohi <- function(n) min(max(7, ceiling(1.5 * n)), 10)
      turvapiir <- function(n) max(2 * n, reliaabluse_pohi(n) + 1)
      n_solme <- length(andmed$solmed)
      
      # AJUTINE DIAGNOSTIKA (19.07.2026) - eemalda pärast juurpõhjuse leidmist.
      # Eesmärk: näha logis täpselt, mis kuju/pikkusega K, solmed, posterior
      # LIVE'is on, kuna standalone-konsoolis (täpselt sama lõpp-andmestikuga)
      # lopeta_test() töötab veatult, aga live'is viskas "'data' must be of
      # a vector type, was 'NULL'" (tõenäoliselt matrix()/apply()-ga seotud).
      message(sprintf("[%s] DIAG enne lopeta_test: n_solme=%s, dim(K)=%s, class(K)=%s, class(solmed)=%s, length(uus_posterior)=%s, class(uus_posterior)=%s",
                      Sys.time(), n_solme,
                      paste(dim(andmed$K), collapse="x"),
                      paste(class(andmed$K), collapse=","),
                      paste(class(andmed$solmed), collapse=","),
                      length(uus_posterior),
                      paste(class(uus_posterior), collapse=",")))
      
      loomulik_valmis <- max(uus_posterior) >= 0.8 && length(uus_kysitud) >= reliaabluse_pohi(n_solme)
      if (loomulik_valmis || length(uus_kysitud) >= turvapiir(n_solme)) {
        peatumise_pohjus <- if (loomulik_valmis) "loomulik" else "turvapiir"
        message(sprintf("[%s] DIAG kutsun lopeta_test(), peatumise_pohjus=%s", Sys.time(), peatumise_pohjus))
        seisund$lopp_profiil <- lopeta_test(
          andmed$test_id, uus_posterior, andmed$solmed, andmed$K, peatumise_pohjus
        )
        message(sprintf("[%s] DIAG lopeta_test() tagastus OK", Sys.time()))
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
      message(sprintf("[%s] EDASI_BTN VIGA test_id=%s: %s", Sys.time(), andmed$test_id, conditionMessage(e)))
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
