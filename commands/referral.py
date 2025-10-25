import discord
from discord import app_commands
from discord.ext import commands
from core.supabase_client import get_table
from core.utils import fmt_money, now_vn, log_info
from core.economy import update_balance

REF_REWARD = 50_000  # người giới thiệu
NEW_USER_REWARD = 20_000  # người được giới thiệu

class Referral(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="referral_link", description="Lấy link mời bạn bè của bạn")
    async def referral_link(self, interaction: discord.Interaction):
        ref_id = interaction.user.id
        link = f"https://discord.gg/YOUR_SERVER_INVITE?ref={ref_id}"
        await interaction.response.send_message(f"🔗 Link giới thiệu của bạn:\n{link}\nMỗi người mời thành công: +{fmt_money(REF_REWARD)}!")

    @app_commands.command(name="referral_use", description="Dùng mã giới thiệu của người khác")
    async def referral_use(self, interaction: discord.Interaction, referrer_id: str):
        user_id = str(interaction.user.id)
        if user_id == referrer_id:
            await interaction.response.send_message("❌ Bạn không thể tự giới thiệu chính mình.")
            return

        table = get_table("referrals")
        exists = table.select("*").eq("user_id", user_id).execute()
        if exists.data:
            await interaction.response.send_message("⚠️ Bạn đã từng nhập mã giới thiệu rồi.")
            return

        table.insert({
            "user_id": user_id,
            "referrer_id": referrer_id,
            "created_at": now_vn().isoformat()
        }).execute()

        await update_balance(referrer_id, REF_REWARD, "Thưởng giới thiệu")
        await update_balance(user_id, NEW_USER_REWARD, "Thưởng người mới")
        await interaction.response.send_message(f"🎁 Bạn đã dùng mã của <@{referrer_id}> và nhận {fmt_money(NEW_USER_REWARD)}!")

    @app_commands.command(name="referral_stats", description="Xem thống kê mời bạn")
    async def referral_stats(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        table = get_table("referrals")
        refs = table.select("*").eq("referrer_id", user_id).execute()
        count = len(refs.data)
        total_reward = count * REF_REWARD

        embed = discord.Embed(
            title="📈 Thống kê Giới thiệu",
            description=f"👥 Số người bạn đã mời: **{count}**\n💰 Tổng thưởng: **{fmt_money(total_reward)}**",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Referral(bot))
