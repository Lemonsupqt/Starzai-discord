"""
Web Search cog — /search and /news commands for real-time information.
Searches the web via DuckDuckGo, feeds results to the LLM as context,
and returns an AI-synthesized answer with source citations.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config.constants import EXPENSIVE_COMMANDS
from utils.embedder import Embedder
from utils.llm_client import LLMClientError
from utils.web_search import WebSearcher

if TYPE_CHECKING:
    from bot import StarzaiBot

logger = logging.getLogger(__name__)

# ── System Prompts ────────────────────────────────────────────────

SEARCH_SYSTEM_PROMPT = (
    "You are Starzai, an AI assistant with real-time web search capabilities. "
    "The user asked a question and web search results have been provided below. "
    "Your job is to synthesize a clear, accurate, and informative answer using "
    "ONLY the information from the search results provided. "
    "Rules:\n"
    "- Be factual and cite information from the sources\n"
    "- If the search results don't contain enough info, say so honestly\n"
    "- Use Discord markdown formatting: **bold**, *italic*, `code`\n"
    "- Keep the response concise but comprehensive (aim for 200-400 words)\n"
    "- When mentioning specific claims, reference which source it came from\n"
    "- Include relevant dates, numbers, and specifics from the results\n"
    "- Do NOT make up information that isn't in the search results\n"
)

NEWS_SYSTEM_PROMPT = (
    "You are Starzai, an AI assistant reporting on current events and breaking news. "
    "Recent news search results have been provided below. "
    "Your job is to synthesize a clear, well-organized news briefing using "
    "ONLY the information from the search results provided. "
    "Rules:\n"
    "- Present the most important/recent developments first\n"
    "- Be factual — cite which source reported what\n"
    "- Include dates, casualty numbers, and concrete details when available\n"
    "- Use Discord markdown: **bold** for key facts, headers for sections\n"
    "- Present multiple perspectives if the sources show different viewpoints\n"
    "- Keep the briefing concise but thorough (aim for 300-500 words)\n"
    "- If covering a conflict/war, include the latest status and key developments\n"
    "- Do NOT speculate beyond what the sources report\n"
)


class SearchCog(commands.Cog, name="Search"):
    """Real-time web search powered by DuckDuckGo + AI synthesis."""

    def __init__(self, bot: StarzaiBot):
        self.bot = bot
        self.searcher = WebSearcher()

    # ── Helpers ───────────────────────────────────────────────────

    async def _gate(
        self, interaction: discord.Interaction, expensive: bool = False
    ) -> bool:
        """Check rate limits. Returns True if allowed."""
        result = self.bot.rate_limiter.check(
            user_id=interaction.user.id,
            server_id=interaction.guild_id,
            expensive=expensive,
        )
        if not result.allowed:
            await interaction.response.send_message(
                embed=Embedder.rate_limited(result.retry_after), ephemeral=True
            )
            return False

        token_result = self.bot.rate_limiter.check_token_budget(
            user_id=interaction.user.id, server_id=interaction.guild_id
        )
        if not token_result.allowed:
            await interaction.response.send_message(
                embed=Embedder.warning("Token Limit", token_result.reason),
                ephemeral=True,
            )
            return False

        return True

    async def _resolve_model(
        self, user_id: int, explicit: Optional[str] = None
    ) -> str:
        if explicit:
            return self.bot.settings.resolve_model(explicit)
        saved = await self.bot.database.get_user_model(user_id)
        if saved:
            return saved
        return self.bot.settings.default_model

    async def _log(
        self,
        interaction: discord.Interaction,
        command: str,
        model: str,
        tokens: int = 0,
        latency_ms: float = 0.0,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        await self.bot.database.log_usage(
            user_id=interaction.user.id,
            command=command,
            guild_id=interaction.guild_id,
            model=model,
            tokens_used=tokens,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
        )
        if tokens:
            await self.bot.database.add_user_tokens(interaction.user.id, tokens)
            self.bot.rate_limiter.record_tokens(
                interaction.user.id, tokens, interaction.guild_id
            )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    # ── /search ───────────────────────────────────────────────────

    @app_commands.command(
        name="search",
        description="Search the web and get an AI-synthesized answer with sources",
    )
    @app_commands.describe(
        query="What to search for (e.g. 'latest Ukraine war updates')",
        model="AI model to use (optional)",
    )
    async def search_cmd(
        self,
        interaction: discord.Interaction,
        query: str,
        model: str = "",
    ) -> None:
        if not await self._gate(interaction, expensive=True):
            return

        await interaction.response.defer()

        # Show searching status
        searching_msg = await interaction.followup.send(
            embed=Embedder.searching(query), wait=True
        )

        resolved_model = await self._resolve_model(interaction.user.id, model or None)
        start = time.monotonic()

        try:
            # Perform web search
            search_response = await self.searcher.search(query)

            if search_response.error:
                await searching_msg.edit(
                    embed=Embedder.error("Search Failed", search_response.error)
                )
                await self._log(
                    interaction, "search", resolved_model,
                    success=False, error_message=search_response.error,
                )
                return

            if not search_response.has_results:
                await searching_msg.edit(
                    embed=Embedder.warning(
                        "No Results",
                        f"No web results found for: **{query}**\n\n"
                        "Try rephrasing your search or using different keywords.",
                    )
                )
                return

            # Format results as LLM context
            search_context = WebSearcher.format_results_for_llm(search_response)

            # Build LLM messages
            messages = [
                {"role": "system", "content": SEARCH_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Question: {query}\n\n"
                        f"Here are the web search results to base your answer on:\n\n"
                        f"{search_context}"
                    ),
                },
            ]

            # Get AI synthesis
            resp = await self.bot.llm.chat(
                messages, model=resolved_model, max_tokens=2048
            )

            latency = (time.monotonic() - start) * 1000

            # Format source links
            sources = WebSearcher.format_sources_for_embed(search_response)

            # Send the final response
            await searching_msg.edit(
                embed=Embedder.search_response(
                    content=resp.content,
                    query=query,
                    sources=sources,
                    search_type="web",
                    cached=search_response.cached,
                )
            )

            await self._log(
                interaction, "search", resolved_model,
                tokens=resp.total_tokens or self._estimate_tokens(query + resp.content),
                latency_ms=latency,
            )

        except LLMClientError as exc:
            logger.error("LLM error in /search: %s", exc)
            await searching_msg.edit(
                embed=Embedder.error("AI Error", f"Search completed but AI synthesis failed: {exc}")
            )
            await self._log(
                interaction, "search", resolved_model,
                success=False, error_message=str(exc),
            )

        except Exception as exc:
            logger.error("Unexpected error in /search: %s", exc, exc_info=True)
            await searching_msg.edit(
                embed=Embedder.error("Error", "Something went wrong. Please try again.")
            )
            await self._log(
                interaction, "search", resolved_model,
                success=False, error_message=str(exc),
            )

    # ── /news ─────────────────────────────────────────────────────

    @app_commands.command(
        name="news",
        description="Get the latest news on any topic with AI-powered briefing",
    )
    @app_commands.describe(
        topic="News topic (e.g. 'Israel Hamas war', 'AI regulation', 'stock market')",
        model="AI model to use (optional)",
    )
    async def news_cmd(
        self,
        interaction: discord.Interaction,
        topic: str,
        model: str = "",
    ) -> None:
        if not await self._gate(interaction, expensive=True):
            return

        await interaction.response.defer()

        # Show searching status
        searching_msg = await interaction.followup.send(
            embed=Embedder.searching(f"📰 {topic}"), wait=True
        )

        resolved_model = await self._resolve_model(interaction.user.id, model or None)
        start = time.monotonic()

        try:
            # Perform news search
            news_response = await self.searcher.search_news(topic)

            if news_response.error:
                await searching_msg.edit(
                    embed=Embedder.error("News Search Failed", news_response.error)
                )
                await self._log(
                    interaction, "news", resolved_model,
                    success=False, error_message=news_response.error,
                )
                return

            if not news_response.has_results:
                await searching_msg.edit(
                    embed=Embedder.warning(
                        "No News Found",
                        f"No recent news found for: **{topic}**\n\n"
                        "Try broadening your topic or checking the spelling.",
                    )
                )
                return

            # Format results as LLM context
            news_context = WebSearcher.format_results_for_llm(news_response)

            # Build LLM messages
            messages = [
                {"role": "system", "content": NEWS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Topic: {topic}\n\n"
                        f"Here are the latest news search results:\n\n"
                        f"{news_context}"
                    ),
                },
            ]

            # Get AI synthesis
            resp = await self.bot.llm.chat(
                messages, model=resolved_model, max_tokens=2048
            )

            latency = (time.monotonic() - start) * 1000

            # Format source links
            sources = WebSearcher.format_sources_for_embed(news_response)

            # Send the final response
            await searching_msg.edit(
                embed=Embedder.search_response(
                    content=resp.content,
                    query=topic,
                    sources=sources,
                    search_type="news",
                    cached=news_response.cached,
                )
            )

            await self._log(
                interaction, "news", resolved_model,
                tokens=resp.total_tokens or self._estimate_tokens(topic + resp.content),
                latency_ms=latency,
            )

        except LLMClientError as exc:
            logger.error("LLM error in /news: %s", exc)
            await searching_msg.edit(
                embed=Embedder.error("AI Error", f"News search completed but AI synthesis failed: {exc}")
            )
            await self._log(
                interaction, "news", resolved_model,
                success=False, error_message=str(exc),
            )

        except Exception as exc:
            logger.error("Unexpected error in /news: %s", exc, exc_info=True)
            await searching_msg.edit(
                embed=Embedder.error("Error", "Something went wrong. Please try again.")
            )
            await self._log(
                interaction, "news", resolved_model,
                success=False, error_message=str(exc),
            )


async def setup(bot: StarzaiBot) -> None:
    await bot.add_cog(SearchCog(bot))

