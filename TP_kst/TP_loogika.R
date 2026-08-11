# =============================================================================
# TP (Testipleier) - R loogika
# =============================================================================

library(httr)
library(jsonlite)
library(kstMatrix)

supabase_key <- Sys.getenv("SUPABASE_SERVICE_KEY")
supabase_url <- "https://kwwxpsrojgtziluguqkm.supabase.co/rest/v1"

# ATA baasaadress(id) - TP peab ATA-t pollima (mitte ainult andmebaasi
# lugema), kuna staatuse-kutse ise käivitab ATA rada 6, kui YP katvus
# on vahepeal täis saanud. Mitu URL-i saab komadega eraldada (koormuse
# jaotamiseks paralleelsete ATA instantside vahel).
ata_base_urls <- Sys.getenv("ATA_BASE_URLS")

vali_ata_url <- function() {
  urlid <- trimws(strsplit(ata_base_urls, ",")[[1]])
  urlid <- urlid[urlid != ""]
  if (length(urlid) == 0) stop("ATA_BASE_URLS on seadistamata.")
  sub("/+$", "", sample(urlid, 1))
}

# Küsib ATA-lt testi edenemise staatust (see päring ise käivitab ATA rada 6,
# kui katvus on täis). Üks automaatne kordus lühikese timeout'i (8s) korral.
kysi_ata_edenemist <- function(test_id) {
  tryCatch({
    res <- GET(paste0(vali_ata_url(), "/api/test/status"),
               query = list(test_id = test_id), timeout(8))
    fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
  }, error = function(e) {
    res <- GET(paste0(vali_ata_url(), "/api/test/status"),
               query = list(test_id = test_id), timeout(8))
    fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
  })
}

# Kaardistab ATA edenemise väljad kasutajasõbralikuks progressitekstiks.
progressi_tekst <- function(vastus) {
  e <- vastus$edenemine
  if (is.null(e) || !isTRUE(e$kst_maatriks_olemas)) return("Testi kavandatakse...")
  if (isTRUE(e$test_aktiivne)) return(NULL)
  if (identical(e$yg_tellimus_staatus, "viga")) {
    return("VIGA")
  }
  if (identical(e$yg_tellimus_esitatud, TRUE) && !isTRUE(e$yg_tellimus_taidetud)) {
    return("Koostame ülesandeid...")
  }
  "Kontrollime hindamist..."
}

if (identical(supabase_key, "")) {
  warning("SUPABASE_SERVICE_KEY keskkonnamuutuja on tühi - Supabase päringud ebaõnnestuvad.")
}

sb_auth_headers <- function() {
  add_headers("apikey" = supabase_key, "Authorization" = paste("Bearer", supabase_key))
}

sb_get <- function(path) {
  res <- GET(paste0(supabase_url, path), sb_auth_headers())
  if (status_code(res) >= 300) stop(sprintf("Supabase GET ebaõnnestus (%s): %s", path, content(res, "text")))
  fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
}

# Kasuta seda (mitte sb_get()+sprintf+URLencode), kui filtri väärtus on vaba
# tekst - httr query= parameeter kodeerib väärtuse täpselt üks kord ise,
# vältides topeltkodeerimise riski, mis muidu jätaks päringu vaikimisi
# tulemuseta (ilma nähtava veata).
sb_get_q <- function(tee, parameetrid) {
  res <- GET(paste0(supabase_url, tee), sb_auth_headers(), query = parameetrid)
  if (status_code(res) >= 300) stop(sprintf("Supabase GET ebaõnnestus (%s): %s", tee, content(res, "text")))
  fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
}

sb_post <- function(path, body_list, prefer = "return=minimal") {
  res <- POST(paste0(supabase_url, path), sb_auth_headers(),
              add_headers("Content-Type" = "application/json", "Prefer" = prefer),
              body = toJSON(body_list, auto_unbox = TRUE, null = "null"), encode = "raw")
  if (status_code(res) >= 300) stop(sprintf("Supabase POST ebaõnnestus (%s): %s", path, content(res, "text")))
  invisible(res)
}

sb_patch <- function(path, body_list) {
  res <- PATCH(paste0(supabase_url, path), sb_auth_headers(),
               add_headers("Content-Type" = "application/json"),
               body = toJSON(body_list, auto_unbox = TRUE, null = "null"), encode = "raw")
  if (status_code(res) >= 300) stop(sprintf("Supabase PATCH ebaõnnestus (%s): %s", path, content(res, "text")))
  invisible(res)
}

# PostgREST tagastab tühja tulemuse list()-ina (pikkus 0), mille nrow()
# annab NULL, mitte 0 - see helper väldib sellest tulenevaid vigu.
n_rida <- function(x) {
  if (is.null(x)) return(0L)
  if (is.data.frame(x)) return(nrow(x))
  length(x)
}

# --- Vastusevariantide järjestus ---------------------------------------------
# Sõnalised variandid: juhuslik järjekord. Arvulised/kuupäevalised/
# kellaajalised: kahanevalt suuruse järgi.
on_numbriline <- function(x) {
  x <- trimws(x)
  !is.na(suppressWarnings(as.numeric(x))) ||
    grepl("^\\d{4}-\\d{2}-\\d{2}", x) ||
    grepl("^\\d{1,2}[:.]\\d{2}", x)
}

numbriline_vaartus <- function(x) {
  x <- trimws(x)
  v <- suppressWarnings(as.numeric(x))
  if (!is.na(v)) return(v)
  d <- suppressWarnings(as.POSIXct(x, tryFormats = c("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%H:%M:%S", "%H:%M")))
  if (!is.na(d)) return(as.numeric(d))
  NA_real_
}

jarjesta_variandid <- function(voti, distraktorid) {
  koik <- c(voti, distraktorid)
  koik <- koik[!is.na(koik) & koik != ""]
  if (length(koik) > 1 && all(sapply(koik, on_numbriline))) {
    koik[order(sapply(koik, numbriline_vaartus), decreasing = TRUE)]
  } else {
    sample(koik)
  }
}

# --- Küsimuse valik (half-split) ---------------------------------------------
# Tagastab veeru-indeksi (sõlme), mis jagab posterior'i kõige ühtlasemalt.
vali_jargmine_solm <- function(posterior, K) {
  kmassesshalfsplit(posterior, K)
}

# --- Bayes-uuendus ------------------------------------------------------------
uuenda_posterior <- function(posterior, K, solm_indeks, vastus_oige, beta, eta) {
  kmassessbayesian(posterior, K, beta, eta, solm_indeks, as.integer(vastus_oige))
}

# Valib ühe sõlme jaoks konkreetse ülesande ylesandepank-ist. Sõlm (mitte
# kursus) on ülesande sobivuse identiteet - kursus on ainult YG jaoks
# materjali leidmise abivahend, mitte ligipääsu piirav filter siin.
# Valikureeglid:
#   1) selle testi jooksul veel KASUTAMATA ülesannete seast eelistatakse
#      väikseima GLOBAALSE kasutamiste_arv-uga (jaotab kasutuse õiglaselt
#      pika aja jooksul kogu poolis)
#   2) kui kõik selle sõlme ülesanded on juba selles testis küsitud (pool
#      ammendunud), valitakse selles TESTIS kõige vähem korratud ülesanne
#      (jaotab kordused õiglaselt testi enda sees)
vali_ylesanne_solmele <- function(solm, kysitud_yp_idd) {
  kandidaadid <- sb_get_q("/ylesandepank", list(
    graafi_objekt = paste0("eq.", solm),
    staatus = "eq.kasutatav",
    select = "yp_id,beeta_error,g_guess,kasutamiste_arv"
  ))
  if (n_rida(kandidaadid) == 0) stop(sprintf("Sõlmele '%s' ei leitud ühtegi kasutatavat ülesannet.", solm))
  
  kasutamata <- kandidaadid[!(kandidaadid$yp_id %in% kysitud_yp_idd), ]
  if (nrow(kasutamata) > 0) {
    valik <- kasutamata[order(kasutamata$kasutamiste_arv), ][1, ]
  } else {
    kysitud_arv <- table(kysitud_yp_idd[kysitud_yp_idd %in% kandidaadid$yp_id])
    kandidaadid$kordi_selles_testis <- sapply(kandidaadid$yp_id, function(id) {
      if (as.character(id) %in% names(kysitud_arv)) kysitud_arv[[as.character(id)]] else 0
    })
    valik <- kandidaadid[order(kandidaadid$kordi_selles_testis), ][1, ]
  }
  
  list(yp_id = valik$yp_id, beta = valik$beeta_error, eta = valik$g_guess,
       kasutamiste_arv = valik$kasutamiste_arv)
}

# --- Ülesande sisu laadimine ---------------------------------------------
lae_ylesanne <- function(yp_id) {
  rida <- sb_get(sprintf("/ylesandepank?yp_id=eq.%s&select=*", yp_id))
  if (n_rida(rida) == 0) stop(sprintf("Ülesannet yp_id=%s ei leitud.", yp_id))
  rida <- rida[1, ]
  list(
    yp_id = rida$yp_id,
    juhis = rida$juhis,
    tyvi = rida$tyvi,
    stiimul = if (length(rida$stiimul) == 0 || is.na(rida$stiimul)) NULL else rida$stiimul,
    voti = rida$voti,
    variandid = jarjesta_variandid(rida$voti, c(rida$distraktor_1, rida$distraktor_2, rida$distraktor_3))
  )
}

# --- Testi täieliku oleku laadimine/algatamine --------------------------------
lae_tp_seisund <- function(test_id) {
  sessioon <- sb_get(sprintf("/testisessioonid?test_id=eq.%s&select=*", test_id))
  if (n_rida(sessioon) == 0) stop("Tundmatu test_id.")
  sessioon <- sessioon[1, ]
  
  if (!identical(sessioon$staatus, "aktiivne")) {
    stop(sprintf("Test ei ole staatuses 'aktiivne' (praegu: %s).", sessioon$staatus))
  }
  
  # Kaitsev JSONB lugemine - väli võib tulla stringina (vajab fromJSON) või
  # juba list-kujul, ja tühja väärtuse korral tagastab vaikimisi tühja list().
  loe_jsonb_vali <- function(toores) {
    if (is.character(toores) && length(toores) >= 1) {
      return(fromJSON(toores[[1]]))
    }
    if (is.list(toores) && length(toores) >= 1) {
      return(toores[[1]])
    }
    list()
  }
  
  testi_loogika <- loe_jsonb_vali(sessioon$testi_loogika)
  tp_seisund <- loe_jsonb_vali(sessioon$tp_seisund)
  
  solmed <- testi_loogika$solmed
  # fromJSON() simplifitseerib JSON massiiv-massiividest automaatselt juba
  # valmis R maatriksiks, kui kõik read on sama pikkusega - kasuta seda
  # otse, kui olemas; muidu ehita käsitsi vektoritest.
  K <- if (is.matrix(testi_loogika$K)) {
    testi_loogika$K
  } else {
    matrix(unlist(testi_loogika$K), nrow = length(testi_loogika$P_K), byrow = TRUE)
  }
  colnames(K) <- solmed
  
  if (length(tp_seisund) == 0) {
    posterior <- unname(testi_loogika$P_K)
    kysitud <- list()
  } else {
    posterior <- unname(tp_seisund$posterior)
    kysitud <- tp_seisund$kysitud
  }
  
  list(
    test_id = test_id,
    metoodika = sessioon$metoodika,
    kursus = sessioon$kursus,
    testi_loogika = testi_loogika,
    solmed = solmed,
    K = K,
    posterior = posterior,
    kysitud = kysitud,
    # Puhtalt informatiivne väli - peatumisreeglid ise elavad app.R-is.
    max_kysimusi = max(2 * length(solmed), min(max(7, ceiling(1.5 * length(solmed))), 10) + 1)
  )
}

salvesta_tp_seisund <- function(test_id, posterior, kysitud) {
  # unname() on kohustuslik: kmassessbayesian() tagastab posterior'i, mille
  # kõik elemendid kannavad sama nime (viimati testitud sõlme järgi) - ilma
  # unname()-ta serialiseeriks toJSON() selle JSON OBJEKTINA (korduvate
  # võtmetega), millest jääks alles ainult viimane väärtus.
  sb_patch(sprintf("/testisessioonid?test_id=eq.%s", test_id), list(
    tp_seisund = toJSON(list(posterior = unname(posterior), kysitud = kysitud), auto_unbox = TRUE)
  ))
}

# Koostab lõpliku tagasiside: leiab usutavate teadmusseisundite hulga C
# (kumulatiivne tõenäosusmass >= tau_tagasiside), ja klassifitseerib iga
# sõlme KÕIGI C hulga olekute suhtes (mitte ainult kõige tõenäolisema
# üksiku oleku suhtes) - nii et ebakindlus KAJASTUB tagasisides, mitte ei
# jää varjatuks.
lopeta_test <- function(test_id, posterior, solmed, K, peatumise_pohjus,
                        tau_tagasiside = 0.9) {
  
  usutavad_olekud <- function(posterior, tau) {
    jarjekord <- order(posterior, decreasing = TRUE)
    kumulatiivne <- cumsum(posterior[jarjekord])
    n <- which(kumulatiivne >= tau)[1]
    if (is.na(n)) n <- length(posterior)
    jarjekord[seq_len(n)]
  }
  
  # Sõlme tasandil neli võimalikku tulemust:
  #   "olemas"        - sõlm kuulub KÕIKIDESSE C olekutesse
  #   "valmis_oppima" - sõlm on väline äär KÕIKIDES C olekutes
  #   "veel_mitte"    - sõlm pole omandatud ega äärel MITTE üheski C olekus
  #   "ebamaarane"    - C hulga olekud lähevad selle sõlme suhtes lahku
  klassifitseeri_solmed <- function(K, solmed, C_indeksid) {
    olekud_info <- lapply(C_indeksid, function(i) {
      olek <- K[i, ]
      list(olek = olek, aar = kmfringe(olek, K))
    })
    klass <- character(length(solmed))
    for (j in seq_along(solmed)) {
      kuulub <- vapply(olekud_info, function(x) x$olek[j] == 1, logical(1))
      valmis <- vapply(olekud_info, function(x) x$aar[j] == 1 && x$olek[j] == 0, logical(1))
      klass[j] <- if (all(kuulub)) {
        "olemas"
      } else if (all(valmis)) {
        "valmis_oppima"
      } else if (!any(kuulub) && !any(valmis)) {
        "veel_mitte"
      } else {
        "ebamaarane"
      }
    }
    setNames(klass, solmed)
  }
  
  C <- usutavad_olekud(posterior, tau_tagasiside)
  klass <- klassifitseeri_solmed(K, solmed, C)
  
  omandatud     <- unname(names(klass)[klass == "olemas"])
  valmis_oppima <- unname(names(klass)[klass == "valmis_oppima"])
  ebamaarane    <- unname(names(klass)[klass == "ebamaarane"])
  veel_mitte    <- unname(names(klass)[klass == "veel_mitte"])
  
  # "Ebamäärane" jaguneb pedagoogiliselt kahte suunda:
  #   ebamaarane_edasi  - sõlm on struktuuriliselt EDASI mõnest juba
  #                        omandatud sõlmest -> ebamäärasus on julgustav
  #                        signaal ("loogiline järgmine samm")
  #   ebamaarane_tagasi - sõlm on struktuuriliselt EELDUS mõnele juba
  #                        omandatud sõlmele -> ebamäärasus on üllatav
  #                        signaal, väärib kordustestimist
  on_eeldus_omandatule <- function(j_indeks, omandatud_indeksid, K) {
    if (length(omandatud_indeksid) == 0) return(FALSE)
    olekud_omandatuga <- apply(K[, omandatud_indeksid, drop = FALSE], 1,
                               function(r) all(r == 1))
    if (!any(olekud_omandatuga)) return(FALSE)
    all(K[olekud_omandatuga, j_indeks] == 1)
  }
  omandatud_indeksid <- which(solmed %in% omandatud)
  ebamaarane_tagasi <- character(0)
  ebamaarane_edasi <- character(0)
  for (s in ebamaarane) {
    j <- which(solmed == s)
    if (on_eeldus_omandatule(j, omandatud_indeksid, K)) {
      ebamaarane_tagasi <- c(ebamaarane_tagasi, s)
    } else {
      ebamaarane_edasi <- c(ebamaarane_edasi, s)
    }
  }
  
  kokkuvote <- if (length(omandatud) == length(solmed)) {
    "Teadsid kõike! Võta uus õpiväljund."
  } else if (length(valmis_oppima) + length(ebamaarane_edasi) > 1) {
    "Sul on nüüd mitu võimalikku suunda, kust jätkata - kõik sobivad järgmiseks võrdselt hästi."
  } else {
    NULL
  }
  
  lopp_profiil <- list(
    omandatud           = omandatud,
    valmis_oppima        = valmis_oppima,
    ebamaarane_edasi     = ebamaarane_edasi,
    ebamaarane_tagasi    = ebamaarane_tagasi,
    veel_mitte           = veel_mitte,
    kokkuvote            = kokkuvote,
    peatumise_pohjus     = peatumise_pohjus,
    kindlus_parim_olek   = max(posterior),
    kindlus_C_hulgas     = sum(posterior[C]),
    n_usutavaid_olekuid  = length(C)
  )
  sb_patch(sprintf("/testisessioonid?test_id=eq.%s", test_id), list(
    staatus = "lõpetatud",
    lopp_profiil = toJSON(lopp_profiil, auto_unbox = TRUE, null = "null")
  ))
  lopp_profiil
}
