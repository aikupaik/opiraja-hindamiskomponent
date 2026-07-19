# =============================================================================
# ATA (Automated Test Assembly) - Plumber API
# Radade loogika:
#   1-2  Tellimuse vastuvõtt + graafi hash                (jagatud kõigi metoodikate vahel)
#   3-4  Teadmusmudeli ehitus (KST struktuur vms)          (metoodika-spetsiifiline)
#   5    YP ülesannete katvuse kontroll + YG käivitus       (jagatud kõigi metoodikate vahel)
#   6    Adaptiivse hindamisloogika koostamine (blim vms)   (metoodika-spetsiifiline)
#
# Praegu on täielikult realiseeritud ainult metoodika = "kst".
# "irt", "dina", "ct" on ette nähtud testisessioonid.metoodika CHECK piiranguga,
# aga rada 3-4 ja 6 viskavad neile hetkel selge vea (vt koosta_teadmusmudel() ja
# koosta_hindamisloogika()) - see on TEADLIK placeholder, mitte unustus.
# =============================================================================

library(plumber)
library(httr)
library(jsonlite)
library(kst)      # Depends: sets, relations - need tulevad library(kst) kaasa
library(digest)
library(uuid)     # test_id genereerimiseks - testisessioonid.test_id veerul ei ole DB defaulti,
# nii et ID tuleb siin, rakenduse poolel, luua enne INSERT-i

# --- Seadistus ---------------------------------------------------------------
# TURVALISUS: võti EI OLE koodis. Sea shinyapps.io projekti
# Settings > Environment variables alt (või kohapeal .Renviron failis):
#   SUPABASE_SERVICE_KEY=...
supabase_key <- Sys.getenv("SUPABASE_SERVICE_KEY")
supabase_url <- "https://kwwxpsrojgtziluguqkm.supabase.co/rest/v1"

# API_VERSIOON - kasutatakse deploy kinnituseks (16.07.2026 debugimise jaoks)
API_VERSIOON <- "2026-07-19-fix-url-encoding"

if (identical(supabase_key, "")) {
  warning("SUPABASE_SERVICE_KEY keskkonnamuutuja on tuhi - Supabase paringud hakkavad ebaonnestuma.")
}

# TP (testipleier) baasaadress(id) - kasutatakse ainult "äratamiseks" testi
# aktiivseks minemisel (fire-and-forget GET). Kui TP-d veel pole deploy'itud,
# jääb see tühjaks ja äratus lihtsalt ignoreeritakse (vt wake_tp() allpool).
# Mitu URL-i saab komadega eraldada (nagu ATA_kst puhul HK_admin's).
tp_base_urls <- Sys.getenv("TP_BASE_URLS")

wake_tp <- function() {
  if (identical(tp_base_urls, "")) return(invisible(NULL))
  urlid <- trimws(strsplit(tp_base_urls, ",")[[1]])
  if (length(urlid) == 0) return(invisible(NULL))
  valitud <- sample(urlid, 1)
  tryCatch({
    GET(valitud, timeout(10))
  }, error = function(e) NULL)  # ignoreerime - kahjutu parim-katse aratus
  invisible(NULL)
}

sb_auth_headers <- function() {
  add_headers(
    "apikey"        = supabase_key,
    "Authorization" = paste("Bearer", supabase_key)
  )
}

# --- HTTP abifunktsioonid koos staatuskoodi kontrolliga -----------------------
# NB: kõik kolm peatavad töötluse selge veateatega, kui Supabase vastab veaga -
# praeguses koodis polnud seda kontrolli üldse, mistõttu vigased/tühjad
# vastused liikusid vaikselt edasi.

sb_get <- function(path_with_query) {
  res <- GET(paste0(supabase_url, path_with_query), sb_auth_headers())
  if (status_code(res) >= 300) {
    stop(sprintf("Supabase GET ebaonnestus (%s): [%s] %s",
                 path_with_query, status_code(res), content(res, "text", encoding = "UTF-8")))
  }
  fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
}

# LISATUD 19.07.2026 - kasuta vaba-teksti filtrite (sõlme/õpiväljundi
# kirjeldus, mitte ID) jaoks - vt täispikk selgitus TP_loogika.R samanimelise
# funktsiooni juures. sb_get()+sprintf+URLencode andis GET()-ile juba
# kord käsitsi kodeeritud stringi tervikuna, mille httr võib URL-i uuesti
# parseerides/kokku pannes TOPELT kodeerida ("," -> "%2C" -> "%252C") -
# tulemuseks 0 rida ilma veata, kuigi andmed on olemas ja õiged. httr
# query= parameeter kodeerib väärtuse TÄPSELT ÜKS KORD, alati turvaline.
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

# NB: LISATUD 17.07.2026 - LEITUD JUURPÕHJUS "argument is of length zero"
# vea korduvale ilmnemisele /api/test/status sees (yg_read kontrollil).
# sb_get() tagastab fromJSON() väljundi: kui PostgREST vastab MITTE-TÜHJA
# massiiviga, tuleb data.frame (nrow() töötab); kui vastus on TÜHI massiiv
# "[]", lihtsustab jsonlite selle tavaliseks list()-iks (pikkus 0), millel
# nrow() tagastab NULL, mitte 0. "if (nrow(x) > 0)" sellise NULL peal viskab
# "argument is of length zero" (NULL > 0 on logical(0), && ei tööta sellega).
# See täpne muster oli juba kontrolli_yp_katvust()-is ja trigger_yg_kui_vaja()-s
# turvaliselt käsitletud ("length(x) == 0 || nrow(x) == 0"), aga status
# endpoint'i yg_read-kontrollil (ja sessioon/graaf kontrollidel) mitte -
# see abifunktsioon koondab turvalise loenduse ühte kohta, nii et edaspidi
# ei saa sama viga kogemata uuesti sisse tulla.
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
  
  # Uus graaf - arvutame KST struktuuri.
  #
  # KINNITATUD ÕIGE (13.07.2026 kohapealne test kasutaja R+kst keskkonnas,
  # 3-sõlmelise ahela A->B->C peal, tulemus täpselt {}, {A}, {A,B}, {A,B,C}):
  # arvutame kehtivad olekud OTSE, mitte kst::endorelation()/kstructure()
  # kaudu suhtest tuletatult - see osutus kolme katse jooksul liiga
  # tundlikuks paketi-spetsiifilise refleksiivsuse/suuna/transitiivsuse
  # konventsiooni suhtes. Alamhulk S on kehtiv teadmusolek, kui iga S-is
  # oleva sõlme kõik OTSESED eeldused on samuti S-is - see katab automaatselt
  # ka kaudsed (transitiivsed) seosed ahelefektina, ilma eraldi transitiivse
  # sulundi arvutamiseta. See loogika katab ühtlasi ka "seoseteta" erijuhu
  # (kui seosed on tühi, on iga alamhulk automaatselt kehtiv - täisruum).
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
  
  # Salvestame uue struktuuri, et järgmine sama graafiga tellimus saaks selle taaskasutada.
  # NB: graafi_struktuur on NOT NULL - salvestame siia algse sõlmede/seoste
  # kirjelduse (kasulik ka hilisemaks silumiseks, kui teadmusruum_maatriks
  # peaks kunagi kahtlaseks jääma).
  # NB: "resolution=ignore-duplicates" katab ära võidujooksu (race condition),
  # mis tekib siis, kui mitu paralleelset ATA instantsi (shinyapps.io
  # koormuse jaotamiseks) üritavad täpselt samal ajal sama graaf_hash-i
  # esimest korda salvestada - PostgREST ignoreerib vaikimisi vea asemel
  # duplikaati, kuna sisu oleks niikuinii deterministlikult identne.
  sb_post("/graafid_kst", list(
    graaf_hash = graaf_hash,
    graafi_struktuur = toJSON(list(solmed = solmed, seosed = seosed), auto_unbox = TRUE),
    teadmusruum_maatriks = toJSON(teadmusruum_raw, auto_unbox = TRUE)
  ), prefer = "return=minimal,resolution=ignore-duplicates")
  
  list(uus = TRUE, teadmusruum = teadmusruum_raw, solmed = solmed)
}

# --- Rada 5: YP katvuse kontroll + YG käivitus (jagatud kõigi metoodikate vahel) --
# NB: eeldab, et YG (Edge function) jälgib yg_tellimused tabelit (nt Supabase
# Database Webhook INSERT peale) ja märgib rea staatuse ise 'tootmises' / 'tehtud'.
# See on ASSUMPTION, kuna YG käivitusmehhanismi täpset lepingut (kas ATA kutsub
# otse Edge Function URL-i, või jälgitakse tabelit) ei ole veel kinnitatud -
# kui YG tegelikult ootab otsest HTTP kutset, tuleb trigger_yg() ümber teha.
kontrolli_yp_katvust <- function(solmed, kursus) {
  # NB: PARANDATUD 15.07.2026 - varasem versioon ehitas ÜHE suure PostgREST
  # "in.(sõlm1,sõlm2,...)" filtri, kus sõlmede nimed ühendati komadega. Kui
  # sõlme enda tekst sisaldab koma (nt "Teab, mis on jõud..." - täiesti
  # tavaline eestikeelses lauses), läks kogu filter katki (PostgREST tõlgendas
  # sõlme-sisest koma täiendava loendi-eraldajana, isegi URL-kodeerituna) -
  # ATA nägi seetõttu ekslikult "puudulikku katvust", kuigi YP oli tegelikult
  # täielikult kaetud. Uus versioon päring iga sõlme kohta ETTE (eq. võrdlus,
  # mitte in. loend) - väldib probleemi täielikult, kuna ühtki väärtust ei
  # ühendata teistega komaga.
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
  
  # Kursus võib puududa (test ilma kursuse/materjalita, ainult õpiväljundite
  # kirjelduse põhjal - YG loob siis ülesanded oma üldteadmiste pealt, vt
  # ai-generator "ALUSMATERJALI KASUTAMISE REEGLID"). yg_tellimused.kursus
  # on NOT NULL andmebaasis, seega ei tohi see kunagi NULL olla - kasutame
  # tühja stringi, mis rahuldab piirangut ja käitub võrdluspäringutes
  # ühtemoodi ("" == "", mitte NULL-i ebamäärane semantika).
  kursus <- if (is.null(kursus)) "" else kursus
  
  sb_post("/yg_tellimused", list(
    test_id          = test_id,
    kursus           = kursus,
    # NB: EI tohi siin käsitsi toJSON()-ida - sb_post() serialiseerib kogu
    # keha juba ise; varasem "toJSON(puuduvad_solmed)" siin tekitas topelt-
    # kodeeringu, mistõttu ai-generator (JS klient) sai graafi_objektid
    # kätte JSON-stringina, mitte päris massiivina, ja tema tellimus.
    # graafi_objektid?.[0] luges stringi ESIMEST TÄHEMÄRKI, mitte massiivi
    # esimest elementi. I() sunnib jsonlite't serialiseerima massiivina ka
    # siis, kui puuduvaid sõlmi on ainult üks (muidu auto_unbox teeks sellest
    # bare stringi, mis oleks JS poolel sama probleem).
    graafi_objektid  = I(puuduvad_solmed),
    kognitiivne_tase = if (is.null(kognitiivne_tase)) "mõistab" else kognitiivne_tase,
    # 3 ülesannet sõlme kohta, et TP saaks vajadusel korduvvaatlusi teha
    # (half-split valik võib sama sõlme kohta rohkem kui korra küsida).
    maht             = 3,
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
  
  # P.K: ühtlane prior üle olekute - lihtsaim esimene versioon.
  P.K <- rep(1 / n_seisundeid, n_seisundeid)
  
  # beta (hooletusviga) ja eta (õnnestunud äraarvamine) iga sõlme jaoks -
  # Variant A: iga sõlm esindatud ühe (praegu kasutuses oleva) YP ülesandega.
  beta <- sapply(solmed, function(s) sõlme_parameetrid[[s]]$beta)
  eta  <- sapply(solmed, function(s) sõlme_parameetrid[[s]]$eta)
  
  # Käsitsi konstrueeritud "blim" klassiga objekt (vt pks dokumentatsiooni
  # endm-i näidet) - EI ole sobitatud andmetest, vaid koostatud olemasolevatest
  # (osaliselt fiktiivsetest, osaliselt kalibreeritud) parameetritest.
  # TP peab selle hiljem taastama ja predict.blim()-iga kasutama.
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
  
  # NB: väljanimed vastavad OR_sim/OR tegelikule tellimuse formaadile
  # (nodes/relations{from,to}/rada_id), mitte varasemale oletatud kujule.
  solmed <- tellimus$nodes
  seosed <- if (is.null(tellimus$relations) || length(tellimus$relations) == 0) {
    data.frame(from = character(0), to = character(0))
  } else {
    as.data.frame(tellimus$relations)
  }
  metoodika <- if (is.null(tellimus$metoodika)) "kst" else tellimus$metoodika
  # Kursus võib puududa (test ilma kursuse/materjalita) - normaliseerime
  # korra siin, et kogu allolev kood (testisessioonid, yg_tellimused) saaks
  # sama väärtuse, mitte NULL vs "" segunemist.
  kursus <- if (is.null(tellimus$kursus)) "" else tellimus$kursus
  
  tulemus <- tryCatch({
    # Rada 1-2
    graaf_hash <- arvuta_graafi_hash(solmed, seosed)
    # test_id ja rada_id: testisessioonid.test_id veerul pole DB defaulti,
    # nii et loome ID siin ise (uuid), ja rada_id tuleb otse tellimusest
    # (tellimuses "õpiraja ID" - tabeli veeru nimi on rada_id).
    test_id <- UUIDgenerate()
    
    # Rada 3-4
    mudel <- koosta_teadmusmudel(metoodika, graaf_hash, solmed, seosed)
    
    # Testisessiooni loomine. staatus jääb vaikeväärtusesse 'planeerimisel' -
    # see väli kirjeldab testi LÄBIVIIMISE (TP) elutsüklit, mitte ATA
    # kokkupaneku etappi, nii et ATA ei tohi siia oma vaheseisundeid kirjutada.
    # ATA "valmisoleku" signaaliks on hoopis testi_loogika sisu (vt allpool
    # ja /api/test/status).
    sb_post("/testisessioonid", list(
      test_id     = test_id,
      graaf_hash  = graaf_hash,
      metoodika   = metoodika,
      kasutaja_id = tellimus$kasutaja_id,
      rada_id     = tellimus$rada_id,
      kursus      = kursus,
      # OR-i tellimuse osa (kasutaja hindamise KAVATSUS - diagnostiline,
      # kvalifikatsioon, suhteline tase, demo/katsetus jne). Väärtuste
      # loend pole veel CHECK-iga piiratud, kuna OR pool pole seda
      # kinnitanud - lisatakse hiljem, kui nimekiri valmis. Kasutatakse
      # tulevikus kalibreerimisel "päris" kasutuse eristamiseks demost.
      eesmark     = tellimus$eesmark
    ), prefer = "return=minimal")
    
    # Rada 5
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
#* 'planeerimisel' -> 'aktiivne' (mudel + reeglid + YP viited on valmis).
#* 'lõpetatud' seisund jääb TP/hilisema analüüsisammu vastutusalasse.
#* @serializer unboxedJSON
#* @get /api/test/status
#* @param test_id
function(test_id) {
  message(sprintf("[%s] /api/test/status KAIVITUS, test_id=%s, API_VERSIOON=%s",
                  Sys.time(), test_id, API_VERSIOON))
  
  # Iga samm saab konteksti-sildi - kui midagi katki läheb, ütleb veateade
  # KOHE, milline samm ebaõnnestus (15.07-16.07.2026 pika debugimise õppetund:
  # üldine "viga" tekst kulutas palju aega, kuni leidsime täpse koha logide
  # kaudu - nüüd on see info kohe veateate sees).
  samm <- function(silt, avaldis) {
    tryCatch(avaldis, error = function(e) {
      message(sprintf("[%s] SAMM EBAONNESTUS: [%s] %s", Sys.time(), silt, conditionMessage(e)))
      stop(sprintf("[%s] %s", silt, conditionMessage(e)), call. = FALSE)
    })
  }
  
  dbg <- function(nimi, x) {
    message(sprintf("[%s] VAARTUS %s: klass=%s pikkus=%s sisu=%s",
                    Sys.time(), nimi, paste(class(x), collapse=","),
                    length(x), paste(utils::capture.output(str(x, max.level=1)), collapse=" | ")))
  }
  
  tryCatch({
    sessioon <- samm("testisessioonid_loe", sb_get(sprintf("/testisessioonid?test_id=eq.%s&select=*", test_id)))
    dbg("sessioon (enne [1,])", sessioon)
    if (n_rida(sessioon) == 0) return(list(viga = "Tundmatu test_id."))
    sessioon <- sessioon[1, ]
    dbg("sessioon$graaf_hash", sessioon$graaf_hash)
    dbg("sessioon$staatus", sessioon$staatus)
    dbg("sessioon$metoodika", sessioon$metoodika)
    dbg("sessioon$testi_loogika", sessioon$testi_loogika)
    
    # yg_tellimused seis selle test_id jaoks (kui üldse esitati) - kasutame
    # seda "edenemine" indikaatorite jaoks, sõltumata sellest, kas YP katvus
    # on juba täielik või mitte.
    yg_read <- samm("yg_tellimused_loe", sb_get(sprintf(
      "/yg_tellimused?test_id=eq.%s&select=staatus&order=id.desc&limit=1", test_id
    )))
    dbg("yg_read", yg_read)
    yg_staatus <- if (n_rida(yg_read) > 0) yg_read$staatus[1] else NA_character_
    dbg("yg_staatus", yg_staatus)
    
    graaf <- samm("graafid_kst_loe", sb_get(sprintf("/graafid_kst?graaf_hash=eq.%s&select=teadmusruum_maatriks", sessioon$graaf_hash)))
    dbg("graaf", graaf)
    kst_olemas <- n_rida(graaf) > 0
    dbg("kst_olemas", kst_olemas)
    
    # NB: kaitsev pikkus-kontroll - kui graaf_hash mingil põhjusel puudub
    # (NULL/length 0, mitte lihtsalt NA), viskaks "!is.na(x) && ..." otse
    # "argument is of length zero" vea, kuna && nõuab mõlemalt poolt
    # pikkust 1. isTRUE()-ga ümbritsemine muudab selle alati pikkus-1
    # loogiliseks, ka siis kui sisemine avaldis peaks olema pikkus 0.
    graaf_hash_val <- sessioon$graaf_hash
    dbg("graaf_hash_val", graaf_hash_val)
    graaf_hash_arvutatud <- isTRUE(length(graaf_hash_val) > 0 && !is.na(graaf_hash_val) && nchar(graaf_hash_val) > 0)
    dbg("graaf_hash_arvutatud", graaf_hash_arvutatud)
    
    edenemine_baas <- list(
      graaf_hash_arvutatud = graaf_hash_arvutatud,
      kst_maatriks_olemas  = kst_olemas,
      yg_tellimus_esitatud = if (is.na(yg_staatus)) "polnud_vaja" else TRUE,
      yg_tellimus_taidetud = if (is.na(yg_staatus)) NA else identical(yg_staatus, "tehtud"),
      yg_tellimus_staatus  = yg_staatus
    )
    dbg("edenemine_baas", edenemine_baas)
    
    # ATA valmisoleku signaal on testi_loogika sisu, MITTE staatus veerg.
    #
    # LEITUD JA PARANDATUD 16.07.2026 - LÕPLIK JUURPÕHJUS pika debugimise
    # järel: kui testi_loogika on veel oma vaikimisi tühi {} (uue testi
    # puhul, mida meie enda kood pole veel kirjutanud), tagastab jsonlite
    # selle 0-VEERUGA DATA.FRAME'INA, MITTE STRINGINA (erinevalt meie enda
    # kirjutatud, topelt-kodeeritud stringist, mis tuleb korrektselt tagasi
    # character(1) kujul). fromJSON() otse data.frame'i peale kutsudes
    # viskas "argument is of length zero" (0-veeruga data.frame length()
    # ongi 0) - täpselt see, mis meid kogu päeva jälitas. Kontrollime nüüd
    # TÜÜPI enne fromJSON() kutsumist.
    testi_loogika_raw <- sessioon$testi_loogika
    kehtiv_loogika <- samm("testi_loogika_parsi", {
      if (is.character(testi_loogika_raw) && length(testi_loogika_raw) == 1 && nchar(testi_loogika_raw) > 0) {
        tryCatch(fromJSON(testi_loogika_raw), error = function(e) list())
      } else {
        list()  # veel kirjutamata (0-veeruga data.frame vms) - käsitleme tühjana
      }
    })
    dbg("kehtiv_loogika", kehtiv_loogika)
    if (length(kehtiv_loogika) > 0) {
      return(list(
        test_id = test_id, staatus = "aktiivne",
        edenemine = c(edenemine_baas, list(test_aktiivne = TRUE)),
        testi_loogika = kehtiv_loogika
      ))
    }
    
    if (!kst_olemas) {
      # Erakorraline seis - ei tohiks juhtuda, kuna create loob selle alati koos.
      return(list(test_id = test_id, staatus = "viga", edenemine = edenemine_baas,
                  viga = "graafid_kst rida puudub - rada 3-4 ei ole korrektselt lõpule jõudnud."))
    }
    
    teadmusruum_raw <- samm("teadmusruum_parsi", fromJSON(graaf$teadmusruum_maatriks[[1]]))
    dbg("teadmusruum_raw", teadmusruum_raw)
    solmed <- unique(unlist(teadmusruum_raw))
    dbg("solmed", solmed)
    
    katvus <- samm("kontrolli_yp_katvust", kontrolli_yp_katvust(solmed, NULL))
    dbg("katvus", katvus)
    
    if (length(katvus$puuduvad_solmed) > 0) {
      return(list(
        test_id = test_id, staatus = "ootel_ylesandeid",
        edenemine = c(edenemine_baas, list(test_aktiivne = FALSE)),
        puuduvad_solmed = katvus$puuduvad_solmed
      ))
    }
    
    # Kõik olemas - rada 6. See ongi hetk, mil sessioon läheb
    # 'planeerimisel' -> 'aktiivne': mudel, reeglid ja kõik YP viited on nüüd
    # olemas. See ÜLEMINEK kuulub ATA vastutusalasse (mitte TP-le) - 'lõpetatud'
    # seevastu vajab lopp_profiil't (reaalsed vastused), mida ATA-l pole, nii
    # et sellesse staatusesse siit ei liiguta.
    hindamisloogika <- samm("koosta_hindamisloogika", koosta_hindamisloogika(sessioon$metoodika, teadmusruum_raw, solmed, katvus$kaetud_solmed))
    
    samm("testisessioonid_uuenda", sb_patch(sprintf("/testisessioonid?test_id=eq.%s", test_id), list(
      staatus       = "aktiivne",
      testi_loogika = toJSON(hindamisloogika, auto_unbox = TRUE)
    )))
    
    # Äratame TP (kui deploy'itud) täpselt siis, kui test valmis saab - annab
    # TP-le maksimaalse puhvriaja, enne kui kasutaja "alusta test" vajutab.
    wake_tp()
    
    list(
      test_id = test_id, staatus = "aktiivne",
      edenemine = c(edenemine_baas, list(test_aktiivne = TRUE)),
      testi_loogika = hindamisloogika
    )
  }, error = function(e) list(viga = conditionMessage(e), api_versioon = API_VERSIOON))
}
