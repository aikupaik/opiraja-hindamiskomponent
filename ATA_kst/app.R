# =============================================================================
# Peidab Plumberi ATA API Shiny rakenduse sisse, et saaks kasutada tasuta
# shinyapps.io majutust, mis mõeldudametlikult toetama Shiny äppe.
#
# NB - VERSIOONITUNDLIKKUS: see kasutab shiny:::joinHandlers, mis on shiny
# paketi EKSPORTIMATA (sisemine) funktsioon. See on aastaid olnud levinud ja
# töötav muster, aga kuna see toetub shiny sisearhitektuurile, tasub see kohapeal
# üle kontrollida enne deploy'd (jooksuta lokaalselt runApp() ja testi
# curl'iga /api/test/create).
#
# ALTERNATIIV: uuemad rsconnect versioonid (vt rsconnect::deployAPI dokumentatsiooni) 
# väidetavalt apkuvad otsest Plumber-API tuge shinyapps.io serveritele,
#  ilma selle "peitmise" trikita. Kui see reaalselt töötab, on see lihtsam ja
#  töökindlam kui allolev(rsconnect::deployAPI(appDir = "."))
# =============================================================================

library(shiny)
library(plumber)

pr <- plumb("api.R")

# Vormilt on äpil UI, sel puudub funktsionaalsus. Katsetamisel näitab lihtsalt, et läks tööle.
ui <- fluidPage(
  titlePanel("Õpiraja hindamiskomponendi API"),
  p("API mootor töötab taustal ja teenindab õpiraja tellimusi ning testi pleierit."),
  tags$ul(
    tags$li(tags$code("POST /api/test/create")),
    tags$li(tags$code("GET /api/test/status?test_id=..."))
  )
)

server <- function(input, output, session) {
# Kogu API loogika käib Plumberi kaudu (vt allpool httpHandler ühendamist),
# mitte siin selle server-funktsiooni kaudu - see jääb siin tühjaks.
}

shiny_app <- shinyApp(ui = ui, server = server)

# See on tegelik "peitmise" mehhanism: liidame Plumberi ruuteri Shiny enda
# HTTP handleri ETTE. Plumber üritab esimesena marsruute sobitada
# (/api/test/create, /api/test/status); kui päring ei sobi ühegi Plumberi
# marsruudiga, kukub see läbi tavalisse Shiny handlerisse (UI kuvamiseks).

shiny_app$httpHandler <- shiny:::joinHandlers(list(
  # Suuname Plumberile AINULT /api/... teed. Ei toetu Plumberi enda n-ö
  # 404-käitumisele (mis tagastaks alati mingi vastuse, mitte NULL,
  # ja takistaks joinHandlers'il kunagi Shiny UI kätte jõudmast).
  function(req) {
    if (startsWith(req$PATH_INFO, "/api/")) pr$call(req) else NULL
  },
  shiny_app$httpHandler
))

shiny_app
