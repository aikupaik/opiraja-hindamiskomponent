# =============================================================================
# ATA (Automated Test Assembly) - Plumber API
# Radade loogika:
#   1-2  Tellimuse vastuvõtt + graafi hash                (jagatud kõigi metoodikate vahel)
#   3-4  Teadmusmudeli ehitus (KST struktuur vms)          (metoodika-spetsiifiline)
#   5    YP ülesannete katvuse kontroll + YG käivitus       (jagatud kõigi metoodikate vahel)
#   6    Adaptiivse hindamisloogika koostamine (blim vms)   (metoodika-spetsiifiline)
#
# Praegu on täielikult realiseeritud ainult metoodika = "kst". "irt", "dina",
# "ct" on ette nähtud testisessioonid.metoodika CHECK piiranguga, aga rada
# 3-4 ja 6 viskavad neile hetkel selge vea - teadlik placeholder.
# =============================================================================

library(plumber)
library(httr)
library(jsonlite)
library(kst)      # Depends: sets, relations - need tulevad library(kst) kaasa
library(digest)
library(uuid)     # test_id genereerimiseks - testisessioonid.test_id veerul pole DB defaulti

# --- Seadistus ---------------------------------------------------------------
# TURVALISUS: võti EI OLE koodis. Sea shinyapps.io projekti
# Settings > Environment variables alt (või kohapeal .Renviron failis):
#   SUPABASE_SERVICE_KEY=...
supabase_key <- Sys.getenv("SUPABASE_SERVICE_KEY")
supabase_url <- "https://kwwxpsrojgtziluguqkm.supabase.co/rest/v1"

API_VERSIOON <- "2026-08-01"

if (identical(supabase_key, "")) {
  warning("SUPABASE_SERVICE_KEY keskkonnamuutuja on tuhi - Supabase paringud hakkavad ebaonnestuma.")
}

# TP baasaadress(id) - kasutatakse ainult "äratamiseks" testi aktiivseks
# minemisel (fire-and-forget GET). Kui TP pole deploy'itud, jääb tühjaks
# ja äratus ignoreeritakse. Mitu URL-i saab komadega eraldada.
tp_base_urls <- Sys.getenv("TP_BASE_URLS")

wake_tp <- function() {
  if (identical(tp_base_urls, "")) return(invisible(NULL))
  urlid <- trimws(strsplit(tp_base_urls, ",")[[1]])
  if (length(urlid) == 0) return(invisible(NULL))
  valitud <- sample(urlid, 1)
  tryCatch({
    GET(valitud, timeout(10))
  }, error = function(e) NULL)
  invisible(NULL)
}

sb_auth_headers <- function() {
  add_headers(
    "apikey"        = supabase_key,
    "Authorization" = paste("Bearer", supabase_key)
  )
}

sb_get <- function(path_with_query) {
  res <- GET(paste0(supabase_url, path_with_query), sb_auth_headers())
  if (status_code(res) >= 300) {
    stop(sprintf("Supabase GET ebaonnestus (%s): [%s] %s",
                 path_with_query, status_code(res), content(res, "text", encoding = "UTF-8")))
  }
  fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
}

# Kasuta vaba-teksti filtrite jaoks (mitte ID/koodi) - httr query= parameeter
# kodeerib väärtuse täpselt üks kord, vältides topeltkodeerimise riski.
sb_get_q <- function(tee, parameetrid) {
  res <- GET(paste0(supabase_url, tee), sb_auth_headers(), query = parameetrid)
  if (status_code(res) >= 300) {
    stop(sprintf("Supabase GET ebaonnestus (%s): [%s] %s",
                 tee, status_code(res), content(res, "text", encoding = "UTF-8")))
  }
  fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
}

sb_post <- function(path, body_list, prefer = "return=representation") {
  res <- POST(
    paste0(supabase_url, path),
    sb_auth_headers(),
    add_headers("Content-Type" = "application/json", "Prefer" = prefer),
    body = toJSON(body_list, auto_unbox = TRUE, null = "null"),
    encode = "raw"
  )
  if (status_code(res) >= 300) {
    stop(sprintf("Supabase POST ebaonnestus (%s): [%s] %s",
                 path, status_code(res), content(res, "text", encoding = "UTF-8")))
  }
  if (identical(prefer, "return=representation")) {
    fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
  } else {
    invisible(res)
  }
}

sb_patch <- function(path_with_query, body_list) {
  res <- PATCH(
    paste0(supabase_url, path_with_query),
    sb_auth_headers(),
    add_headers("Content-Type" = "application/json"),
    body = toJSON(body_list, auto_unbox = TRUE, null = "null"),
    encode = "raw"
  )
  if (status_code(res) >= 300) {
    stop(sprintf("Supabase PATCH ebaonnestus (%s): [%s] %s",
                 path_with_query, status_code(res), content(res, "text", encoding = "UTF-8")))
  }
  invisible(res)
}

# PostgREST tagastab tühja tulemuse list()-ina (pikkus 0), mille nrow()
# annab NULL, mitte 0 - see helper väldib sellest tulenevaid vigu.
n_rida <- function(x) {
  if (is.null(x)) return(0L)
  if (is.data.frame(x)) return(nrow(x))
  length(x)
}

# --- Rada 1-2: graafi hash ----------------------------------------------------
# Hash arvutatakse sõlmede ja sõltuvuste kanoonilisest (sorteeritud) esitusest,
# et sama graaf annaks sama hashi sõltumata sisendi järjekorrast.
arvuta_graafi_hash <- function(solmed, seosed) {
  kanooniline <- list(
    solmed = sort(unique(solmed)),
    seosed = seosed[order(seosed[[1]], seosed[[2]]), , drop = FALSE]
  )
  digest(kanooniline, algo = "sha256")
}

# --- Rada 3-4: teadmusmudeli ehitus (metoodika-spetsiifiline) -----------------
koosta_teadmusmudel <- function(metoodika, graaf_hash, solmed, seosed) {
  if (metoodika != "kst") {
    stop(sprintf(
      "Metoodika '%s' teadmusmudeli ehitus pole veel implementeeritud. Praegu toetatud: kst.",
      metoodika
    ))
  }

  # Kas see graaf_hash on juba varem arvutatud ja salvestatud?
  olemasolev <- sb_get(sprintf(
    "/graafid_kst?graaf_hash=eq.%s&select=graaf_hash,teadmusruum_maatriks", graaf_hash
  ))

  if (length(olemasolev) > 0 && nrow(olemasolev) > 0) {
    teadmusruum_raw <- fromJSON(olemasolev$teadmusruum_maatriks[[1]])
    return(list(uus = FALSE, teadmusruum = teadmusruum_raw, solmed = solmed))
  }

  # Uus graaf - arvutame KST struktuuri otse (mitte kst::endorelation()/
  # kstructure() suhtest tuletatult): alamhulk S on kehtiv teadmusolek, kui
  # iga S-is oleva sõlme kõik OTSESED eeldused on samuti S-is - see katab
  # automaatselt ka kaudsed (transitiivsed) seosed ahelefektina.
  on_kehtiv_olek <- function(S, seosed) {
    if (nrow(seosed) == 0) return(TRUE)
    for (i in seq_len(nrow(seosed))) {
      eeldus <- seosed[i, 1]
      solmus <- seosed[i, 2]
      if (solmus %in% S && !(eeldus %in% S)) return(FALSE)
    }
    TRUE
  }

  koik_alamhulgad <- unlist(
    lapply(0:length(solmed), function(k) combn(solmed, k, simplify = FALSE)),
    recursive = FALSE
  )
  kehtivad_olekud <- Filter(function(S) on_kehtiv_olek(S, seosed), koik_alamhulgad)
  struktuur <- kstructure(as.set(lapply(kehtivad_olekud, as.set)))

  teadmusruum_raw <- lapply(as.list(struktuur), function(s) as.character(s))

  # "resolution=ignore-duplicates" katab võidujooksu, kui mitu paralleelset
  # ATA instantsi üritavad täpselt samal ajal sama graaf_hash-i salvestada.
  sb_post("/graafid_kst", list(
    graaf_hash = graaf_hash,
    graafi_struktuur = toJSON(list(solmed = solmed, seosed = seosed), auto_unbox = TRUE),
    teadmusruum_maatriks = toJSON(teadmusruum_raw, auto_unbox = TRUE)
  ), prefer = "return=minimal,resolution=ignore-duplicates")

  list(uus = TRUE, teadmusruum = teadmusruum_raw, solmed = solmed)
}

# --- Rada 5: YP katvuse kontroll + YG käivitus (jagatud kõigi metoodikate vahel) --
# Eeldab, et YG (Edge Function) jälgib yg_tellimused tabelit (Supabase Database
# Webhook INSERT peale) ja märgib rea staatuse ise 'tootmises' / 'tehtud'.
kontrolli_yp_katvust <- function(solmed, kursus) {
  # Iga sõlme kohta eraldi eq.-päring (mitte üks koondatud in.(...) loend) -
  # väldib probleemi, kui sõlme tekst ise sisaldab koma.
  kaetud_list <- list()
  puuduvad <- c()
  for (s in solmed) {
    tulemus <- sb_get_q("/ylesandepank", list(
      graafi_objekt = paste0("eq.", s),
      staatus = "eq.kasutatav",
      select = "yp_id,beeta_error,g_guess",
      limit = "1"
    ))
    if (length(tulemus) == 0 || nrow(tulemus) == 0) {
      puuduvad <- c(puuduvad, s)
    } else {
      kaetud_list[[s]] <- list(
        yp_id = tulemus$yp_id[1],
        beta  = tulemus$beeta_error[1],
        eta   = tulemus$g_guess[1]
      )
    }
  }

  list(kaetud_solmed = kaetud_list, puuduvad_solmed = puuduvad)
}

trigger_yg_kui_vaja <- function(test_id, kursus, kognitiivne_tase, puuduvad_solmed) {
  if (length(puuduvad_solmed) == 0) return(invisible(NULL))

  # Ei dubleeri tellimust, kui selle test_id jaoks on juba pooleliolev YG tellimus.
  pooleli <- sb_get(sprintf(
    "/yg_tellimused?test_id=eq.%s&staatus=in.(ootel,tootmises)&select=id", test_id
  ))
  if (length(pooleli) > 0 && nrow(pooleli) > 0) return(invisible(NULL))

  # Kursus võib puududa (test ilma kursuse/materjalita - YG loob siis
  # ülesanded oma üldteadmiste pealt). yg_tellimused.kursus on NOT NULL,
  # nii et kasutame tühja stringi, mitte NULL-i.
  kursus <- if (is.null(kursus)) "" else kursus

  sb_post("/yg_tellimused", list(
    test_id          = test_id,
    kursus           = kursus,
    # I() sunnib jsonlite't serialiseerima massiivina ka siis, kui
    # puuduvaid sõlmi on ainult üks (muidu auto_unbox teeks bare stringi).
    graafi_objektid  = I(puuduvad_solmed),
    kognitiivne_tase = if (is.null(kognitiivne_tase)) "mõistab" else kognitiivne_tase,
    # 5 ülesannet sõlme kohta - annab TP-le piisava varu korduvvaatlusteks
    # (half-split võib sama sõlme kohta rohkem kui korra küsida).
    maht             = 5,
    staatus          = "ootel"
  ), prefer = "return=minimal")

  invisible(NULL)
}

# --- Rada 6: adaptiivse hindamisloogika koostamine (metoodika-spetsiifiline) --
koosta_hindamisloogika <- function(metoodika, teadmusruum_raw, solmed, sõlme_parameetrid) {
  if (metoodika != "kst") {
    stop(sprintf(
      "Metoodika '%s' hindamisloogika koostamine pole veel implementeeritud. Praegu toetatud: kst.",
      metoodika
    ))
  }

  # K: olekute x sõlmede 0/1 maatriks (BLIM-i formaat).
  K <- t(sapply(teadmusruum_raw, function(seisund) as.integer(solmed %in% seisund)))
  colnames(K) <- solmed
  n_seisundeid <- nrow(K)

  P.K <- rep(1 / n_seisundeid, n_seisundeid)

  # beta (hooletusviga) ja eta (õnnestunud äraarvamine) iga sõlme jaoks -
  # praegu ühe (kasutuses oleva) YP ülesande enda parameetrite kaudu.
  beta <- sapply(solmed, function(s) sõlme_parameetrid[[s]]$beta)
  eta  <- sapply(solmed, function(s) sõlme_parameetrid[[s]]$eta)

  list(
    metoodika = "kst",
    K         = K,
    P_K       = setNames(P.K, apply(K, 1, function(r) paste(solmed[r == 1], collapse = ","))),
    solmed    = solmed,
    beta      = setNames(beta, solmed),
    eta       = setNames(eta, solmed),
    yp_id     = setNames(sapply(solmed, function(s) sõlme_parameetrid[[s]]$yp_id), solmed),
    ntotal    = 0,
    koostatud = as.character(Sys.time())
  )
}

# =============================================================================
# ENDPOINTS
# =============================================================================

#* Loo uus testisessioon: rada 1-5. EI jää ootama YP täitumist - kui midagi
#* puudub, jääb sessioon staatusesse 'ootel_ylesandeid' ja klient küsib
#* /api/test/status kaudu hiljem uuesti.
#* @serializer unboxedJSON
#* @post /api/test/create
function(req) {
  tellimus <- tryCatch(fromJSON(req$postBody), error = function(e) NULL)
  if (is.null(tellimus)) {
    return(list(viga = "Tellimuse JSON-i ei õnnestunud parsida."))
  }

  # Väljanimed vastavad OR tellimuse formaadile (nodes/relations{from,to}/rada_id).
  solmed <- tellimus$nodes
  seosed <- if (is.null(tellimus$relations) || length(tellimus$relations) == 0) {
    data.frame(from = character(0), to = character(0))
  } else {
    as.data.frame(tellimus$relations)
  }
  metoodika <- if (is.null(tellimus$metoodika)) "kst" else tellimus$metoodika
  kursus <- if (is.null(tellimus$kursus)) "" else tellimus$kursus

  tulemus <- tryCatch({
    graaf_hash <- arvuta_graafi_hash(solmed, seosed)
    test_id <- UUIDgenerate()

    mudel <- koosta_teadmusmudel(metoodika, graaf_hash, solmed, seosed)

    # staatus jääb vaikeväärtusesse 'planeerimisel' - ATA "valmisoleku"
    # signaaliks on testi_loogika sisu (vt /api/test/status), mitte see väli.
    sb_post("/testisessioonid", list(
      test_id     = test_id,
      graaf_hash  = graaf_hash,
      metoodika   = metoodika,
      kasutaja_id = tellimus$kasutaja_id,
      rada_id     = tellimus$rada_id,
      kursus      = kursus,
      eesmark     = tellimus$eesmark
    ), prefer = "return=minimal")

    katvus <- kontrolli_yp_katvust(solmed, kursus)
    trigger_yg_kui_vaja(test_id, kursus, tellimus$kognitiivne_tase, katvus$puuduvad_solmed)

    list(
      test_id         = test_id,
      staatus         = if (length(katvus$puuduvad_solmed) == 0) "ylesanded_olemas" else "ootel_ylesandeid",
      puuduvad_solmed = katvus$puuduvad_solmed
    )
  }, error = function(e) list(viga = conditionMessage(e), api_versioon = API_VERSIOON))

  tulemus
}

#* Küsi testisessiooni staatust. Kui kõik YP ülesanded on nüüdseks olemas,
#* käivitab siin (mitte create-s) rada 6 ja viib testisessiooni staatuse
#* 'planeerimisel' -> 'aktiivne'. 'lõpetatud' seisund jääb TP vastutusalasse.
#* @serializer unboxedJSON
#* @get /api/test/status
#* @param test_id
function(test_id) {
  samm <- function(silt, avaldis) {
    tryCatch(avaldis, error = function(e) {
      stop(sprintf("[%s] %s", silt, conditionMessage(e)), call. = FALSE)
    })
  }

  tryCatch({
    sessioon <- samm("testisessioonid_loe", sb_get(sprintf("/testisessioonid?test_id=eq.%s&select=*", test_id)))
    if (n_rida(sessioon) == 0) return(list(viga = "Tundmatu test_id."))
    sessioon <- sessioon[1, ]

    yg_read <- samm("yg_tellimused_loe", sb_get(sprintf(
      "/yg_tellimused?test_id=eq.%s&select=staatus&order=id.desc&limit=1", test_id
    )))
    yg_staatus <- if (n_rida(yg_read) > 0) yg_read$staatus[1] else NA_character_

    graaf <- samm("graafid_kst_loe", sb_get(sprintf("/graafid_kst?graaf_hash=eq.%s&select=teadmusruum_maatriks", sessioon$graaf_hash)))
    kst_olemas <- n_rida(graaf) > 0

    graaf_hash_val <- sessioon$graaf_hash
    graaf_hash_arvutatud <- isTRUE(length(graaf_hash_val) > 0 && !is.na(graaf_hash_val) && nchar(graaf_hash_val) > 0)

    edenemine_baas <- list(
      graaf_hash_arvutatud = graaf_hash_arvutatud,
      kst_maatriks_olemas  = kst_olemas,
      yg_tellimus_esitatud = if (is.na(yg_staatus)) "polnud_vaja" else TRUE,
      yg_tellimus_taidetud = if (is.na(yg_staatus)) NA else identical(yg_staatus, "tehtud"),
      yg_tellimus_staatus  = yg_staatus
    )

    # ATA valmisoleku signaal on testi_loogika SISU, mitte staatus veerg -
    # veel kirjutamata väli tuleb 0-veeruga data.frame'ina, mitte stringina,
    # nii et kontrollime tüüpi enne fromJSON()-i.
    testi_loogika_raw <- sessioon$testi_loogika
    kehtiv_loogika <- samm("testi_loogika_parsi", {
      if (is.character(testi_loogika_raw) && length(testi_loogika_raw) == 1 && nchar(testi_loogika_raw) > 0) {
        tryCatch(fromJSON(testi_loogika_raw), error = function(e) list())
      } else {
        list()
      }
    })
    if (length(kehtiv_loogika) > 0) {
      return(list(
        test_id = test_id, staatus = "aktiivne",
        edenemine = c(edenemine_baas, list(test_aktiivne = TRUE)),
        testi_loogika = kehtiv_loogika
      ))
    }

    if (!kst_olemas) {
      return(list(test_id = test_id, staatus = "viga", edenemine = edenemine_baas,
                  viga = "graafid_kst rida puudub - rada 3-4 ei ole korrektselt lõpule jõudnud."))
    }

    teadmusruum_raw <- samm("teadmusruum_parsi", fromJSON(graaf$teadmusruum_maatriks[[1]]))
    solmed <- unique(unlist(teadmusruum_raw))

    katvus <- samm("kontrolli_yp_katvust", kontrolli_yp_katvust(solmed, NULL))

    if (length(katvus$puuduvad_solmed) > 0) {
      return(list(
        test_id = test_id, staatus = "ootel_ylesandeid",
        edenemine = c(edenemine_baas, list(test_aktiivne = FALSE)),
        puuduvad_solmed = katvus$puuduvad_solmed
      ))
    }

    # Kõik olemas - rada 6, sessioon läheb 'planeerimisel' -> 'aktiivne'.
    hindamisloogika <- samm("koosta_hindamisloogika", koosta_hindamisloogika(sessioon$metoodika, teadmusruum_raw, solmed, katvus$kaetud_solmed))

    samm("testisessioonid_uuenda", sb_patch(sprintf("/testisessioonid?test_id=eq.%s", test_id), list(
      staatus       = "aktiivne",
      testi_loogika = toJSON(hindamisloogika, auto_unbox = TRUE)
    )))

    # Äratame TP (kui deploy'itud) täpselt siis, kui test valmis saab.
    wake_tp()

    list(
      test_id = test_id, staatus = "aktiivne",
      edenemine = c(edenemine_baas, list(test_aktiivne = TRUE)),
      testi_loogika = hindamisloogika
    )
  }, error = function(e) list(viga = conditionMessage(e), api_versioon = API_VERSIOON))
}