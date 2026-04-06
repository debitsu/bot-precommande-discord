import discord
import os
import json
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = 1031649449098879007
SPREADSHEET_ID = "1BKNIai_ofjBVaKlYte6ACotQeWmOat_ZC2y9mkJ7tOk"

SHEET_NAMES = [
    "Individual",
    "Group of 5",
    "Group of 10",
    "1 clan",
    "2 clans",
    "3 clans",
    "Global",
]

OBJECTIF_TOTAL = 7000

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

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


def lire_lignes(sheet_name):
    service = get_sheets_service()
    range_name = f"{sheet_name}!A:H"

    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute()

    return result.get("values", [])


def convertir_bool(valeur):
    texte = str(valeur).strip().upper()
    return texte in ["TRUE", "VRAI", "1", "YES"]


def parser_produit(gorgon_val, imp_val):
    gorgon = convertir_bool(gorgon_val)
    imp = convertir_bool(imp_val)

    if gorgon and imp:
        return "combo"
    if gorgon:
        return "gorgon"
    if imp:
        return "imp"
    return None


def convertir_prix(prix_str):
    prix_str = str(prix_str).strip().lower()
    prix_str = prix_str.replace("$", "")
    prix_str = prix_str.replace("€", "")
    prix_str = prix_str.replace(" ", "")
    prix_str = prix_str.replace(",", ".")

    try:
        return float(prix_str)
    except ValueError:
        return 0.0


def recuperer_donnees_sheet_simple(sheet_name):
    lignes = lire_lignes(sheet_name)

    categories = {
        "gorgon": [],
        "imp": [],
        "combo": []
    }

    total_prix = 0.0

    for ligne in lignes[1:]:
        discord_id = ligne[0].strip() if len(ligne) > 0 else ""
        hrid = ligne[1].strip() if len(ligne) > 1 else ""
        gorgon_val = ligne[2].strip() if len(ligne) > 2 else ""
        imp_val = ligne[3].strip() if len(ligne) > 3 else ""
        prix = ligne[4].strip() if len(ligne) > 4 else ""
        payment = ligne[5].strip() if len(ligne) > 5 else ""
        date_val = ligne[6].strip() if len(ligne) > 6 else ""
        identifiant_h = ligne[7].strip() if len(ligne) > 7 else ""

        produit = parser_produit(gorgon_val, imp_val)

        if not discord_id and not hrid and not identifiant_h:
            continue

        if produit:
            categories[produit].append({
                "discord_id": discord_id or "Inconnu",
                "hrid": hrid or "Inconnu",
                "prix": prix,
                "payment": payment,
                "date": date_val,
                "identifiant_h": identifiant_h
            })

        total_prix += convertir_prix(prix)

    return categories, total_prix


def recuperer_donnees(sheet_name):
    if sheet_name == "Global":
        categories_total = {
            "gorgon": [],
            "imp": [],
            "combo": []
        }
        total_prix_global = 0.0

        autres_onglets = [s for s in SHEET_NAMES if s != "Global"]

        for onglet in autres_onglets:
            categories, total_prix = recuperer_donnees_sheet_simple(onglet)

            categories_total["gorgon"].extend(categories["gorgon"])
            categories_total["imp"].extend(categories["imp"])
            categories_total["combo"].extend(categories["combo"])

            total_prix_global += total_prix

        return categories_total, total_prix_global

    return recuperer_donnees_sheet_simple(sheet_name)


def recuperer_detail_global():
    details = []
    total_general = 0.0

    autres_onglets = [s for s in SHEET_NAMES if s != "Global"]

    for onglet in autres_onglets:
        categories, total_prix = recuperer_donnees_sheet_simple(onglet)
        details.append({
            "sheet_name": onglet,
            "total_prix": total_prix,
            "gorgon": len(categories["gorgon"]),
            "imp": len(categories["imp"]),
            "combo": len(categories["combo"]),
        })
        total_general += total_prix

    return details, total_general


def formater_joueurs(joueurs):
    if not joueurs:
        return "Aucun joueur"

    lignes = []
    for joueur in joueurs:
        lignes.append(f"**{joueur['discord_id']}** — `{joueur['hrid']}`")

    texte = "\n".join(lignes)

    if len(texte) > 4000:
        texte = texte[:4000] + "\n..."

    return texte


def formater_identifiants_h(joueurs):
    identifiants = [
        j["identifiant_h"].strip()
        for j in joueurs
        if j.get("identifiant_h") and j["identifiant_h"].strip()
    ]

    if not identifiants:
        return "Aucun identifiant"

    texte = ",".join(identifiants)

    if len(texte) > 3800:
        texte = texte[:3800] + "..."

    return texte


def creer_contenu_export_identifiants(sheet_name):
    categories, _ = recuperer_donnees(sheet_name)

    gorgon_ids = formater_identifiants_h(categories["gorgon"])
    imp_ids = formater_identifiants_h(categories["imp"])
    combo_ids = formater_identifiants_h(categories["combo"])

    contenu = (
        f"GORGON\n{gorgon_ids}\n\n"
        f"IMP\n{imp_ids}\n\n"
        f"COMBO\n{combo_ids}\n"
    )

    return contenu


def creer_embed_categorie(sheet_name, nom_categorie, joueurs, couleur):
    titres = {
        "gorgon": "🟢 Liste Gorgon",
        "imp": "🔴 Liste Imp",
        "combo": "🟡 Liste Combo"
    }

    embed = discord.Embed(
        title=titres[nom_categorie],
        description=f"Onglet : **{sheet_name}**\nNombre de joueurs : **{len(joueurs)}**",
        color=couleur
    )

    texte = formater_joueurs(joueurs)

    if len(texte) <= 1024:
        embed.add_field(name="Joueurs", value=texte, inline=False)
    else:
        morceaux = []
        courant = ""

        for ligne in texte.split("\n"):
            if len(courant) + len(ligne) + 1 > 1024:
                morceaux.append(courant)
                courant = ligne
            else:
                courant = ligne if not courant else courant + "\n" + ligne

        if courant:
            morceaux.append(courant)

        for i, morceau in enumerate(morceaux[:25], start=1):
            embed.add_field(name=f"Joueurs ({i})", value=morceau, inline=False)

    embed.set_footer(text="Bot liste produits")
    return embed


def creer_embed_identifiants_h(sheet_name, nom_categorie, joueurs, couleur):
    titres = {
        "gorgon": "🟢 Liste identifiants Gorgon",
        "imp": "🔴 Liste identifiants Imp",
        "combo": "🟡 Liste identifiants Combo"
    }

    embed = discord.Embed(
        title=titres[nom_categorie],
        description=f"Onglet : **{sheet_name}**\nIdentifiants de la colonne H séparés par `,`",
        color=couleur
    )

    texte = formater_identifiants_h(joueurs)
    embed.add_field(name="Identifiants", value=f"```{texte}```", inline=False)
    embed.set_footer(text="Copier-coller direct")
    return embed


def creer_embed_stats_global():
    details, total_general = recuperer_detail_global()

    total_gorgon = sum(item["gorgon"] for item in details)
    total_imp = sum(item["imp"] for item in details)
    total_combo = sum(item["combo"] for item in details)

    pourcentage = (total_general / OBJECTIF_TOTAL) * 100 if OBJECTIF_TOTAL > 0 else 0

    total_general_affiche = int(total_general) if total_general.is_integer() else round(total_general, 2)
    pourcentage_affiche = round(pourcentage, 2)

    embed = discord.Embed(
        title="📊 Statistiques Globales",
        description="Somme de tous les onglets hors `Global`",
        color=0x5865F2
    )

    embed.add_field(name="🟢 Total Gorgon", value=str(total_gorgon), inline=False)
    embed.add_field(name="🔴 Total Imp", value=str(total_imp), inline=False)
    embed.add_field(name="🟡 Total Combo", value=str(total_combo), inline=False)
    embed.add_field(
        name="💰 Progression financière",
        value=f"{total_general_affiche} / {OBJECTIF_TOTAL} ({pourcentage_affiche}%)",
        inline=False
    )

    lignes_detail = []
    for item in details:
        prix = int(item["total_prix"]) if item["total_prix"].is_integer() else round(item["total_prix"], 2)
        lignes_detail.append(
            f"**{item['sheet_name']}** : {prix} "
            f"(G:{item['gorgon']} / I:{item['imp']} / C:{item['combo']})"
        )

    texte_detail = "\n".join(lignes_detail) if lignes_detail else "Aucune donnée"

    if len(texte_detail) > 1024:
        texte_detail = texte_detail[:1000] + "\n..."

    embed.add_field(
        name="📂 Détail par onglet",
        value=texte_detail,
        inline=False
    )

    embed.set_footer(text="Bot liste produits")
    return embed


class ListeIdentifiantsHView(discord.ui.View):
    def __init__(self, sheet_name):
        super().__init__(timeout=180)
        self.sheet_name = sheet_name

    @discord.ui.button(label="Gorgon", style=discord.ButtonStyle.success, emoji="🟢")
    async def bouton_gorgon(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees(self.sheet_name)
            embed = creer_embed_identifiants_h(self.sheet_name, "gorgon", categories["gorgon"], 0x2ecc71)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur liste identifiants H gorgon :", e)
            await interaction.followup.send(
                "❌ Erreur lors de la récupération des identifiants.",
                ephemeral=True
            )

    @discord.ui.button(label="Imp", style=discord.ButtonStyle.danger, emoji="🔴")
    async def bouton_imp(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees(self.sheet_name)
            embed = creer_embed_identifiants_h(self.sheet_name, "imp", categories["imp"], 0xe74c3c)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur liste identifiants H imp :", e)
            await interaction.followup.send(
                "❌ Erreur lors de la récupération des identifiants.",
                ephemeral=True
            )

    @discord.ui.button(label="Combo", style=discord.ButtonStyle.primary, emoji="🟡")
    async def bouton_combo(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees(self.sheet_name)
            embed = creer_embed_identifiants_h(self.sheet_name, "combo", categories["combo"], 0xf1c40f)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur liste identifiants H combo :", e)
            await interaction.followup.send(
                "❌ Erreur lors de la récupération des identifiants.",
                ephemeral=True
            )

    @discord.ui.button(label="Exporter", style=discord.ButtonStyle.secondary, emoji="📁")
    async def bouton_exporter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)

            contenu = creer_contenu_export_identifiants(self.sheet_name)
            fichier = discord.File(
                io.BytesIO(contenu.encode("utf-8")),
                filename=f"identifiants_{self.sheet_name.lower().replace(' ', '_')}.txt"
            )

            await interaction.followup.send(
                content="📁 Export des identifiants prêt :",
                file=fichier,
                ephemeral=True
            )
        except Exception as e:
            print("Erreur export identifiants H :", e)
            await interaction.followup.send(
                "❌ Erreur lors de l'export des identifiants.",
                ephemeral=True
            )


class GlobalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Total Gorgon", style=discord.ButtonStyle.success, emoji="🟢")
    async def bouton_total_gorgon(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees("Global")
            embed = creer_embed_categorie("Global", "gorgon", categories["gorgon"], 0x2ecc71)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton total gorgon global :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des données globales.", ephemeral=True)

    @discord.ui.button(label="Total Imp", style=discord.ButtonStyle.danger, emoji="🔴")
    async def bouton_total_imp(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees("Global")
            embed = creer_embed_categorie("Global", "imp", categories["imp"], 0xe74c3c)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton total imp global :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des données globales.", ephemeral=True)

    @discord.ui.button(label="Total Combo", style=discord.ButtonStyle.primary, emoji="🟡")
    async def bouton_total_combo(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees("Global")
            embed = creer_embed_categorie("Global", "combo", categories["combo"], 0xf1c40f)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton total combo global :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des données globales.", ephemeral=True)

    @discord.ui.button(label="Stat", style=discord.ButtonStyle.secondary, emoji="📊")
    async def bouton_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            embed = creer_embed_stats_global()
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton stats global :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des statistiques globales.", ephemeral=True)

    @discord.ui.button(label="Identifiants H", style=discord.ButtonStyle.secondary, emoji="🆔")
    async def bouton_identifiants_h(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            embed = discord.Embed(
                title="🆔 Identifiants H globaux",
                description="Choisis une catégorie pour afficher les valeurs de la colonne H cumulées.",
                color=0x5865F2
            )
            embed.add_field(
                name="Options",
                value="🟢 Gorgon\n🔴 Imp\n🟡 Combo\n📁 Exporter",
                inline=False
            )
            await interaction.response.send_message(
                embed=embed,
                view=ListeIdentifiantsHView("Global"),
                ephemeral=True
            )
        except Exception as e:
            print("Erreur bouton identifiants H global :", e)
            await interaction.response.send_message(
                "❌ Erreur lors de l'ouverture des identifiants H globaux.",
                ephemeral=True
            )


class CategoryButtonsView(discord.ui.View):
    def __init__(self, sheet_name):
        super().__init__(timeout=180)
        self.sheet_name = sheet_name

    @discord.ui.button(label="Gorgon", style=discord.ButtonStyle.success, emoji="🟢")
    async def bouton_gorgon(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees(self.sheet_name)
            embed = creer_embed_categorie(self.sheet_name, "gorgon", categories["gorgon"], 0x2ecc71)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton gorgon :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des données.", ephemeral=True)

    @discord.ui.button(label="Imp", style=discord.ButtonStyle.danger, emoji="🔴")
    async def bouton_imp(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees(self.sheet_name)
            embed = creer_embed_categorie(self.sheet_name, "imp", categories["imp"], 0xe74c3c)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton imp :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des données.", ephemeral=True)

    @discord.ui.button(label="Combo", style=discord.ButtonStyle.primary, emoji="🟡")
    async def bouton_combo(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees(self.sheet_name)
            embed = creer_embed_categorie(self.sheet_name, "combo", categories["combo"], 0xf1c40f)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton combo :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des données.", ephemeral=True)


class SheetActionView(discord.ui.View):
    def __init__(self, sheet_name):
        super().__init__(timeout=180)
        self.sheet_name = sheet_name

    @discord.ui.button(label="Catégories", style=discord.ButtonStyle.primary, emoji="📦")
    async def bouton_categories(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            embed = discord.Embed(
                title="📦 Catégories",
                description=f"Onglet : **{self.sheet_name}**",
                color=0x5865F2
            )
            embed.add_field(
                name="Options",
                value="🟢 Gorgon\n🔴 Imp\n🟡 Combo",
                inline=False
            )
            await interaction.response.send_message(
                embed=embed,
                view=CategoryButtonsView(self.sheet_name),
                ephemeral=True
            )
        except Exception as e:
            print("Erreur action catégories :", e)
            await interaction.response.send_message("❌ Erreur.", ephemeral=True)


class SheetSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=sheet_name, value=sheet_name)
            for sheet_name in SHEET_NAMES
        ]

        super().__init__(
            placeholder="Choisis un onglet",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        sheet_name = self.values[0]

        embed = discord.Embed(
            title="📂 Onglet sélectionné",
            description=f"Tu as choisi **{sheet_name}**.",
            color=0x5865F2
        )

        if sheet_name == "Global":
            embed.add_field(
                name="Options disponibles",
                value="🟢 Total Gorgon\n🔴 Total Imp\n🟡 Total Combo\n📊 Stat\n🆔 Identifiants H",
                inline=False
            )
            await interaction.response.send_message(
                embed=embed,
                view=GlobalView(),
                ephemeral=True
            )
        else:
            embed.add_field(
                name="Options disponibles",
                value="📦 Catégories",
                inline=False
            )
            await interaction.response.send_message(
                embed=embed,
                view=SheetActionView(sheet_name),
                ephemeral=True
            )


class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(SheetSelect())


@client.event
async def on_ready():
    print(f"Connecté en tant que {client.user}")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id != CHANNEL_ID:
        return

    if message.content.strip().lower() == "!menu":
        embed = discord.Embed(
            title="📦 Menu des produits",
            description="Choisis d’abord un onglet.",
            color=0x5865F2
        )
        embed.add_field(
            name="Onglets disponibles",
            value="\n".join([f"• {name}" for name in SHEET_NAMES]),
            inline=False
        )
        embed.set_footer(text="Les résultats s'affichent en privé")

        await message.channel.send(embed=embed, view=MainMenuView())
        return


if not TOKEN:
    raise ValueError("TOKEN manquant dans Railway")

client.run(TOKEN)
