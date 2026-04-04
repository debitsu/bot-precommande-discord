import discord
import os
import json
import re
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

PRIX_GROUPES = {
    "1": "PRIX_1",
    "5": "PRIX_5",
    "10": "PRIX_10",
    "1 clan": "PRIX_1_CLAN",
    "2 clan": "PRIX_2_CLAN",
    "3 clan": "PRIX_3_CLAN",
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
    prix_str = str(prix_str).strip().lower()
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


def recuperer_pledges_utilisateur(auteur_discord):
    lignes = lire_toutes_les_lignes()
    pledges = []

    for numero_ligne, ligne in enumerate(lignes[1:], start=2):
        pseudo_colonne = ligne[1].strip() if len(ligne) > 1 else ""
        hrid = ligne[2].strip() if len(ligne) > 2 else ""
        id_supp = ligne[3].strip() if len(ligne) > 3 else ""
        produit = ligne[4].strip() if len(ligne) > 4 else ""
        groupe = ligne[5].strip() if len(ligne) > 5 else ""
        prix = ligne[6].strip() if len(ligne) > 6 else ""
        auteur_reel = ligne[7].strip() if len(ligne) > 7 else ""
        lien = ligne[8].strip() if len(ligne) > 8 else ""

        if pseudo_colonne == auteur_discord or auteur_reel == auteur_discord:
            pledges.append({
                "numero_ligne": numero_ligne,
                "pseudo": pseudo_colonne,
                "hrid": hrid,
                "id_supplementaire": id_supp,
                "produit": produit,
                "groupe": groupe,
                "prix": prix,
                "auteur_reel": auteur_reel,
                "lien": lien
            })

    return pledges


async def traiter_commande_data(data, auteur_reel, lien_message):
    lignes_existantes = trouver_lignes_par_hrid(data["hrid"])

    if not lignes_existantes:
        ajouter_ligne(
            data=data,
            auteur_reel=auteur_reel,
            lien_message=lien_message
        )
        print("Nouvelle précommande ajoutée :", data)
        return "✅ Précommande enregistrée dans le tableur."

    for _, ligne_existante in lignes_existantes:
        ancienne_data = extraire_donnees_ligne_existante(ligne_existante)
        if commandes_identiques(data, ancienne_data):
            return "⚠️ Cette commande existe déjà pour ce HR ID. Aucune modification faite."

    lignes_a_supprimer = []
    for numero_ligne, ligne_existante in lignes_existantes:
        ancienne_data = extraire_donnees_ligne_existante(ligne_existante)
        if nouvelle_couvre_ancienne(data, ancienne_data):
            lignes_a_supprimer.append(numero_ligne)

    for numero_ligne in sorted(lignes_a_supprimer, reverse=True):
        supprimer_ligne(numero_ligne)

    ajouter_ligne(
        data=data,
        auteur_reel=auteur_reel,
        lien_message=lien_message
    )

    if lignes_a_supprimer:
        return "✅ Commande enregistrée et ancienne commande inférieure remplacée."

    return "✅ Nouvelle commande enregistrée sans supprimer les précédentes."


class HRIDModal(discord.ui.Modal, title="Finaliser la précommande"):
    hr_ids = discord.ui.TextInput(
        label="HR ID(s)",
        placeholder="Un par ligne, ou séparés par virgule",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    id_supplementaire = discord.ui.TextInput(
        label="ID supplémentaire (optionnel)",
        placeholder="Laisse vide si non utilisé",
        required=False,
        max_length=200
    )

    def __init__(self, produit, groupe, prix, auteur):
        super().__init__()
        self.produit = produit
        self.groupe = groupe
        self.prix = prix
        self.auteur = auteur

    async def on_submit(self, interaction: discord.Interaction):
        contenu = self.hr_ids.value.strip()

        hr_ids = [
            x.strip()
            for x in re.split(r"[\n,;]+", contenu)
            if x.strip()
        ]

        if not hr_ids:
            await interaction.response.send_message(
                "❌ Aucun HR ID valide détecté.",
                ephemeral=True
            )
            return

        resultats = []

        for hrid in hr_ids:
            data = {
                "pseudo": str(self.auteur),
                "hrid": hrid,
                "id_supplementaire": self.id_supplementaire.value.strip(),
                "produit": self.produit,
                "groupe": self.groupe,
                "prix": self.prix,
            }

            try:
                resultat = await traiter_commande_data(
                    data=data,
                    auteur_reel=str(self.auteur),
                    lien_message=f"Interaction Discord - user {self.auteur.id}"
                )
                resultats.append(f"**{hrid}** : {resultat}")
            except Exception as e:
                print("Erreur Google Sheets :", e)
                resultats.append(f"**{hrid}** : ❌ Erreur lors de l'enregistrement.")

        embed = discord.Embed(
            title="📦 Résultat de la précommande",
            description=f"Produit : **{self.produit}**\nGroupe : **{self.groupe}**\nPrix : **{self.prix}**",
            color=0x2ecc71
        )

        texte = "\n".join(resultats)
        if len(texte) > 3500:
            texte = texte[:3500] + "\n..."

        embed.add_field(name="HR ID traités", value=texte or "Aucun", inline=False)
        embed.set_footer(text=f"Demande envoyée par {self.auteur}")

        await interaction.response.send_message(embed=embed, ephemeral=True)


class GroupeSelect(discord.ui.Select):
    def __init__(self, auteur, produit):
        self.auteur = auteur
        self.produit = produit

        options = [
            discord.SelectOption(label="1", description=f"Prix : {PRIX_GROUPES['1']}"),
            discord.SelectOption(label="5", description=f"Prix : {PRIX_GROUPES['5']}"),
            discord.SelectOption(label="10", description=f"Prix : {PRIX_GROUPES['10']}"),
            discord.SelectOption(label="1 clan", description=f"Prix : {PRIX_GROUPES['1 clan']}"),
            discord.SelectOption(label="2 clan", description=f"Prix : {PRIX_GROUPES['2 clan']}"),
            discord.SelectOption(label="3 clan", description=f"Prix : {PRIX_GROUPES['3 clan']}"),
        ]

        super().__init__(
            placeholder="Choisis le groupe",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.auteur.id:
            await interaction.response.send_message(
                "❌ Ce menu n'est pas pour toi.",
                ephemeral=True
            )
            return

        groupe = self.values[0]
        prix = PRIX_GROUPES[groupe]

        modal = HRIDModal(
            produit=self.produit,
            groupe=groupe,
            prix=prix,
            auteur=self.auteur
        )
        await interaction.response.send_modal(modal)


class GroupeView(discord.ui.View):
    def __init__(self, auteur, produit):
        super().__init__(timeout=180)
        self.add_item(GroupeSelect(auteur=auteur, produit=produit))


class ProduitView(discord.ui.View):
    def __init__(self, auteur):
        super().__init__(timeout=180)
        self.auteur = auteur

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.auteur.id:
            await interaction.response.send_message(
                "❌ Cette précommande n'est pas pour toi.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Gorgon", style=discord.ButtonStyle.primary)
    async def gorgon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Choisis maintenant le groupe :",
            view=GroupeView(self.auteur, "gorgon skin"),
            ephemeral=True
        )

    @discord.ui.button(label="Imp", style=discord.ButtonStyle.danger)
    async def imp(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Choisis maintenant le groupe :",
            view=GroupeView(self.auteur, "imp master skin"),
            ephemeral=True
        )

    @discord.ui.button(label="Gorgon + Imp", style=discord.ButtonStyle.success)
    async def combo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Choisis maintenant le groupe :",
            view=GroupeView(self.auteur, "gorgon skin + imp master skin"),
            ephemeral=True
        )


class SupprimerPledgeSelect(discord.ui.Select):
    def __init__(self, auteur, pledges):
        self.auteur = auteur
        self.pledges = pledges

        options = []
        for pledge in pledges[:25]:
            label = f"{pledge['produit']} | HR ID {pledge['hrid']}"
            description = f"Groupe: {pledge['groupe']} | Prix: {pledge['prix']}"
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    description=description[:100],
                    value=str(pledge["numero_ligne"])
                )
            )

        super().__init__(
            placeholder="Choisis le pledge à supprimer",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.auteur.id:
            await interaction.response.send_message(
                "❌ Ce menu n'est pas pour toi.",
                ephemeral=True
            )
            return

        numero_ligne = int(self.values[0])

        try:
            supprimer_ligne(numero_ligne)
            await interaction.response.send_message(
                "✅ Le pledge sélectionné a été supprimé du Google Sheet. Relance `!mespledges` pour voir la liste mise à jour.",
                ephemeral=True
            )
        except Exception as e:
            print("Erreur suppression pledge :", e)
            await interaction.response.send_message(
                "❌ Erreur lors de la suppression du pledge.",
                ephemeral=True
            )


class SupprimerPledgeView(discord.ui.View):
    def __init__(self, auteur, pledges):
        super().__init__(timeout=180)
        self.add_item(SupprimerPledgeSelect(auteur=auteur, pledges=pledges))


@client.event
async def on_ready():
    print(f"Connecté en tant que {client.user}")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id != CHANNEL_ID:
        return

    if message.content.strip().lower() == "!pledge":
        embed = discord.Embed(
            title="📦 Nouvelle précommande",
            description="Choisis ton produit avec les boutons ci-dessous.",
            color=0x3498db
        )
        embed.add_field(
            name="Produit",
            value="Gorgon / Imp / Gorgon + Imp",
            inline=False
        )
        embed.set_footer(text="Le reste se fera étape par étape")

        await message.channel.send(
            embed=embed,
            view=ProduitView(message.author)
        )
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

    if message.content.strip().lower() == "!mespledges":
        try:
            auteur_discord = str(message.author)
            pledges = recuperer_pledges_utilisateur(auteur_discord)

            if not pledges:
                await message.author.send("📭 Aucun pledge actif trouvé pour ton pseudo.")
                await message.reply("📩 Je t'ai envoyé le résultat en privé.", mention_author=False)
                return

            embed = discord.Embed(
                title="📦 Tes pledges actifs",
                description=f"Pledges trouvés pour **{auteur_discord}**",
                color=0x3498db
            )

            for i, pledge in enumerate(pledges[:25], start=1):
                valeur = (
                    f"**HR ID :** {pledge['hrid']}\n"
                    f"**ID supplémentaire :** {pledge['id_supplementaire'] or '—'}\n"
                    f"**Produit :** {pledge['produit']}\n"
                    f"**Groupe :** {pledge['groupe']}\n"
                    f"**Prix :** {pledge['prix']}"
                )

                if pledge["lien"]:
                    valeur += f"\n**Lien :** {pledge['lien']}"

                embed.add_field(
                    name=f"Pledge #{i}",
                    value=valeur,
                    inline=False
                )

            embed.set_footer(text="Choisis dans le menu ci-dessous si tu veux supprimer un pledge")

            await message.author.send(
                embed=embed,
                view=SupprimerPledgeView(message.author, pledges)
            )
            await message.reply(
                "📩 Je t'ai envoyé tes pledges actifs en privé, avec une option de suppression.",
                mention_author=False
            )

        except discord.Forbidden:
            await message.reply(
                "❌ Impossible de t'envoyer un message privé. Active tes MP puis réessaie.",
                mention_author=False
            )
        except Exception as e:
            print("Erreur mespledges :", e)
            await message.reply(
                "❌ Erreur lors de la récupération de tes pledges.",
                mention_author=False
            )
        return

    data, erreur = parse_message(message.content)

    if erreur:
        await message.reply(erreur, mention_author=False)
        return

    try:
        resultat = await traiter_commande_data(
            data=data,
            auteur_reel=str(message.author),
            lien_message=message.jump_url
        )
        await message.reply(resultat, mention_author=False)

    except Exception as e:
        print("Erreur Google Sheets :", e)
        await message.reply(
            "❌ Erreur lors de l'enregistrement dans le tableur.",
            mention_author=False
        )


if not TOKEN:
    raise ValueError("TOKEN manquant dans Railway")

client.run(TOKEN)