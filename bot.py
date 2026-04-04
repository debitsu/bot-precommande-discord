import discord
import os
import json
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = 1490001972064161924
SPREADSHEET_ID = "1TwgZ7fZV0ot90Sn7Vlpucuro8y5dGoS6Vgi0uwvZgwg"
RANGE_NAME = "Feuille 1!A:I"
SHEET_NAME = "Feuille 1"

GROUPES_AUTORISES = ["1", "5", "10", "1 clan", "2 clan", "3 clan"]

VALEUR_GROUPE = {
    "1": 1,
    "5": 5,
    "10": 10,
    "1 clan": 50,
    "2 clan": 100,
    "3 clan": 150
}

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

client = discord.Client(intents=intents)


def get_sheets_service():
    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

    if not credentials_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON manquant")

    creds_dict = json.loads(credentials_json)

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )

    return build("sheets", "v4", credentials=creds)


def normaliser_texte(texte):
    texte = texte.strip().lower()
    texte = " ".join(texte.split())
    return texte


def normaliser_produit(produit_brut):
    produit = normaliser_texte(produit_brut)

    correspondances = {
        "gorgon skin": "gorgon skin",
        "gorgon": "gorgon skin",
        "imp master skin": "imp master skin",
        "imp skin": "imp master skin",
        "imp master": "imp master skin",
        "imp": "imp master skin",
        "gorgon skin + imp master skin": "gorgon skin + imp master skin",
        "gorgon + imp": "gorgon skin + imp master skin",
        "gorgon skin + imp": "gorgon skin + imp master skin",
        "gorgon + imp master skin": "gorgon skin + imp master skin",
        "gorgon skin+imp master skin": "gorgon skin + imp master skin",
        "gorgon skin +imp master skin": "gorgon skin + imp master skin",
        "gorgon skin+ imp master skin": "gorgon skin + imp master skin",
        "gorgon/imp": "gorgon skin + imp master skin",
        "gorgon + imp master": "gorgon skin + imp master skin",
    }

    return correspondances.get(produit)


def parse_message(content):
    data = {}
    lignes = content.split("\n")

    for ligne in lignes:
        ligne = ligne.strip()
        ligne_min = ligne.lower()

        if "pseudo discord" in ligne_min:
            data["pseudo"] = ligne.split(":")[-1].strip()

        elif "hr id" in ligne_min:
            data["hrid"] = ligne.split(":")[-1].strip()

        elif "id suplementaire" in ligne_min or "id supplémentaire" in ligne_min:
            data["id_supplementaire"] = ligne.split(":")[-1].strip()

        elif "produit" in ligne_min:
            produit_brut = ligne.split(":")[-1].strip()
            data["produit"] = normaliser_produit(produit_brut)

        elif "groupe" in ligne_min:
            data["groupe"] = normaliser_texte(ligne.split(":")[-1].strip())

        elif "prix" in ligne_min:
            data["prix"] = ligne.split(":")[-1].strip()

    if len(data) != 6:
        return None, (
            "❌ Format invalide. Merci de remplir les 6 lignes demandées.\n\n"
            "Format attendu :\n"
            "1: Pseudo discord: ...\n"
            "2: HR ID : ...\n"
            "3: ID supplémentaire : ...\n"
            "4: produit : ...\n"
            "5: groupe: ...\n"
            "6: prix : ..."
        )

    if not data["produit"]:
        return None, (
            "❌ Produit invalide.\n"
            "Produits autorisés :\n"
            "- gorgon skin\n"
            "- imp master skin\n"
            "- gorgon skin + imp master skin"
        )

    if data["groupe"] not in GROUPES_AUTORISES:
        return None, (
            "❌ Groupe invalide.\n"
            "Valeurs autorisées : 1, 5, 10, 1 clan, 2 clan, 3 clan."
        )

    return data, None


def lire_toutes_les_lignes():
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGE_NAME
    ).execute()
    return result.get("values", [])


def get_sheet_id_by_name():
    service = get_sheets_service()
    spreadsheet = service.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID
    ).execute()

    for sheet in spreadsheet.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == SHEET_NAME:
            return props.get("sheetId")

    raise ValueError(f"Onglet '{SHEET_NAME}' introuvable dans le tableur.")


def trouver_lignes_par_hrid(hrid):
    lignes = lire_toutes_les_lignes()
    resultats = []

    for i, ligne in enumerate(lignes[1:], start=2):
        if len(ligne) >= 3:
            hrid_existant = ligne[2].strip()
            if hrid_existant == hrid:
                resultats.append((i, ligne))

    return resultats


def supprimer_ligne(numero_ligne):
    service = get_sheets_service()
    sheet_id = get_sheet_id_by_name()

    requests = [{
        "deleteDimension": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": numero_ligne - 1,
                "endIndex": numero_ligne
            }
        }
    }]

    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests}
    ).execute()


def ajouter_ligne(data, auteur_reel, lien_message):
    service = get_sheets_service()

    values = [[
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        data["pseudo"],
        data["hrid"],
        data["id_supplementaire"],
        data["produit"],
        data["groupe"],
        data["prix"],
        auteur_reel,
        lien_message
    ]]

    body = {"values": values}

    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGE_NAME,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()


def extraire_donnees_ligne_existante(ligne):
    return {
        "pseudo": ligne[1].strip() if len(ligne) > 1 else "",
        "hrid": ligne[2].strip() if len(ligne) > 2 else "",
        "id_supplementaire": ligne[3].strip() if len(ligne) > 3 else "",
        "produit": normaliser_produit(ligne[4].strip()) if len(ligne) > 4 else None,
        "groupe": normaliser_texte(ligne[5].strip()) if len(ligne) > 5 else "",
        "prix": ligne[6].strip() if len(ligne) > 6 else ""
    }


def commande_vers_quantites(data):
    quantite = VALEUR_GROUPE[data["groupe"]]

    if data["produit"] == "gorgon skin":
        return {"gorgon skin": quantite, "imp master skin": 0}

    if data["produit"] == "imp master skin":
        return {"gorgon skin": 0, "imp master skin": quantite}

    if data["produit"] == "gorgon skin + imp master skin":
        return {"gorgon skin": quantite, "imp master skin": quantite}

    return {"gorgon skin": 0, "imp master skin": 0}


def commandes_identiques(cmd1, cmd2):
    return (
        cmd1["produit"] == cmd2["produit"]
        and cmd1["groupe"] == cmd2["groupe"]
    )


def nouvelle_couvre_ancienne(nouvelle, ancienne):
    q_n = commande_vers_quantites(nouvelle)
    q_a = commande_vers_quantites(ancienne)

    couvre_tout = (
        q_n["gorgon skin"] >= q_a["gorgon skin"]
        and q_n["imp master skin"] >= q_a["imp master skin"]
    )

    strictement_mieux = (
        q_n["gorgon skin"] > q_a["gorgon skin"]
        or q_n["imp master skin"] > q_a["imp master skin"]
    )

    return couvre_tout and strictement_mieux


def convertir_prix_en_nombre(prix_str):
    prix_str = prix_str.strip().lower()
    prix_str = prix_str.replace(" ", "")
    prix_str = prix_str.replace("€", "")
    prix_str = prix_str.replace("$", "")
    prix_str = prix_str.replace(",", ".")

    try:
        return float(prix_str)
    except ValueError:
        return 0.0


def calculer_stats():
    lignes = lire_toutes_les_lignes()

    total_gorgon = 0
    total_imp = 0
    total_combo = 0
    total_prix = 0.0

    for ligne in lignes[1:]:
        data = extraire_donnees_ligne_existante(ligne)

        if not data["produit"] or not data["groupe"]:
            continue

        quantite = VALEUR_GROUPE.get(data["groupe"], 0)

        if data["produit"] == "gorgon skin":
            total_gorgon += quantite

        elif data["produit"] == "imp master skin":
            total_imp += quantite

        elif data["produit"] == "gorgon skin + imp master skin":
            total_combo += quantite
            total_gorgon += quantite
            total_imp += quantite

        total_prix += convertir_prix_en_nombre(data["prix"])

    return {
        "total_gorgon": total_gorgon,
        "total_imp": total_imp,
        "total_combo": total_combo,
        "total_prix": total_prix
    }


@client.event
async def on_ready():
    print(f"Connecté en tant que {client.user}")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id != CHANNEL_ID:
        return

    if message.content.strip().lower() == "!stats":
        try:
            stats = calculer_stats()

            total_prix_affiche = (
                int(stats["total_prix"])
                if stats["total_prix"].is_integer()
                else stats["total_prix"]
            )

            embed = discord.Embed(
                title="📊 Statistiques précommandes",
                description="Résumé actuel des commandes enregistrées",
                color=0x2ecc71
            )

            embed.add_field(
                name="🟢 Total Gorgon",
                value=str(stats["total_gorgon"]),
                inline=False
            )
            embed.add_field(
                name="🔴 Total Imp",
                value=str(stats["total_imp"]),
                inline=False
            )
            embed.add_field(
                name="🟡 Total Combo",
                value=str(stats["total_combo"]),
                inline=False
            )
            embed.add_field(
                name="💰 Total Prix",
                value=str(total_prix_affiche),
                inline=False
            )

            embed.set_footer(text="Mise à jour en temps réel depuis Google Sheets")

            await message.channel.send(embed=embed)

        except Exception as e:
            print("Erreur stats :", e)
            await message.channel.send("❌ Erreur lors du calcul des statistiques.")
        return

    data, erreur = parse_message(message.content)

    if erreur:
        await message.reply(erreur, mention_author=False)
        return

    try:
        lignes_existantes = trouver_lignes_par_hrid(data["hrid"])

        if not lignes_existantes:
            ajouter_ligne(
                data=data,
                auteur_reel=str(message.author),
                lien_message=message.jump_url
            )
            print("Nouvelle précommande ajoutée :", data)
            await message.reply("✅ Précommande enregistrée dans le tableur.", mention_author=False)
            return

        for _, ligne_existante in lignes_existantes:
            ancienne_data = extraire_donnees_ligne_existante(ligne_existante)
            if commandes_identiques(data, ancienne_data):
                await message.reply(
                    "⚠️ Cette commande existe déjà pour ce HR ID. Aucune modification faite.",
                    mention_author=False
                )
                return

        lignes_a_supprimer = []
        for numero_ligne, ligne_existante in lignes_existantes:
            ancienne_data = extraire_donnees_ligne_existante(ligne_existante)
            if nouvelle_couvre_ancienne(data, ancienne_data):
                lignes_a_supprimer.append(numero_ligne)

        for numero_ligne in sorted(lignes_a_supprimer, reverse=True):
            supprimer_ligne(numero_ligne)

        ajouter_ligne(
            data=data,
            auteur_reel=str(message.author),
            lien_message=message.jump_url
        )

        if lignes_a_supprimer:
            await message.reply(
                "✅ Commande enregistrée et ancienne commande inférieure remplacée.",
                mention_author=False
            )
        else:
            await message.reply(
                "✅ Nouvelle commande enregistrée sans supprimer les précédentes.",
                mention_author=False
            )

        print("Commande traitée :", data)

    except Exception as e:
        print("Erreur Google Sheets :", e)
        await message.reply(
            "❌ Erreur lors de l'enregistrement dans le tableur.",
            mention_author=False
        )


if not TOKEN:
    raise ValueError("TOKEN manquant dans Railway")

client.run(TOKEN)