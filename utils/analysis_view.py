"""
Interactive paginated view for user analysis results.
Provides navigation buttons, model switching, and PDF/text downloads.
"""

import discord
from typing import List, Dict, Any, Optional, Callable
import io
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT


class AnalysisView(discord.ui.View):
    """Interactive paginated view for displaying comprehensive user analysis."""
    
    def __init__(
        self,
        pages: List[discord.Embed],
        full_report: str,
        user_name: str,
        message_count: int,
        analysis_data: Dict[str, Any],
        messages: List[Dict[str, Any]],
        reanalyze_callback: Optional[Callable] = None,
        timeout: float = 900
    ):
        """
        Initialize the analysis view.
        
        Args:
            pages: List of embed pages to display
            full_report: Full text report for download
            user_name: Name of analyzed user
            message_count: Number of messages analyzed
            analysis_data: Structured analysis data
            messages: Raw message data for re-analysis
            reanalyze_callback: Async function to call for re-analysis with different model
            timeout: View timeout in seconds (default 15 minutes)
        """
        super().__init__(timeout=timeout)
        self.pages = pages
        self.full_report = full_report
        self.user_name = user_name
        self.message_count = message_count
        self.analysis_data = analysis_data
        self.messages = messages
        self.reanalyze_callback = reanalyze_callback
        self.current_page = 0
        self.message: discord.Message = None
        
        # Update button states
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current page."""
        # Disable previous button on first page
        self.previous_button.disabled = (self.current_page == 0)
        
        # Disable next button on last page
        self.next_button.disabled = (self.current_page == len(self.pages) - 1)
        
        # Update page indicator
        self.page_indicator.label = f"Page {self.current_page + 1}/{len(self.pages)}"
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary, custom_id="previous", row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, custom_id="page_indicator", disabled=True, row=0)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Page indicator (non-interactive)."""
        pass
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary, custom_id="next", row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.success, custom_id="home", row=0)
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to first page."""
        self.current_page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="📥 Download TXT", style=discord.ButtonStyle.secondary, custom_id="download_txt", row=1)
    async def download_txt_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Download full report as text file."""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"analysis_{self.user_name.replace(' ', '_')}_{timestamp}.txt"
        
        file_content = self.full_report.encode('utf-8')
        file = discord.File(io.BytesIO(file_content), filename=filename)
        
        await interaction.response.send_message(
            f"📄 **Text Report for {self.user_name}**",
            file=file,
            ephemeral=True
        )
    
    @discord.ui.button(label="📕 Download PDF", style=discord.ButtonStyle.secondary, custom_id="download_pdf", row=1)
    async def download_pdf_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Download full report as beautifully formatted PDF."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d")
            filename = f"analysis_{self.user_name.replace(' ', '_')}_{timestamp}.pdf"
            
            # Generate PDF
            pdf_buffer = io.BytesIO()
            pdf = generate_pdf_report(
                pdf_buffer,
                self.analysis_data,
                self.user_name,
                self.message_count
            )
            
            pdf_buffer.seek(0)
            file = discord.File(pdf_buffer, filename=filename)
            
            await interaction.followup.send(
                f"📕 **PDF Report for {self.user_name}**\n"
                f"*Professional formatted analysis with {self.message_count:,} messages*",
                file=file,
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error generating PDF: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="🔄 Re-analyze", style=discord.ButtonStyle.primary, custom_id="reanalyze", row=1)
    async def reanalyze_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Re-analyze with a different model."""
        if not self.reanalyze_callback:
            await interaction.response.send_message(
                "❌ Re-analysis not available for this report.",
                ephemeral=True
            )
            return
        
        # Show model selection modal
        await interaction.response.send_modal(ModelSelectionModal(self.reanalyze_callback, self.messages, self.user_name))
    
    async def on_timeout(self):
        """Called when the view times out."""
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        # Update message if it exists
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass


class ModelSelectionModal(discord.ui.Modal, title="Re-analyze with Different Model"):
    """Modal for selecting a different AI model for re-analysis."""
    
    model_input = discord.ui.TextInput(
        label="Model Name",
        placeholder="e.g., gpt-4, claude-3-opus, gemini-pro",
        default="gpt-4",
        max_length=50
    )
    
    def __init__(self, reanalyze_callback: Callable, messages: List[Dict[str, Any]], user_name: str):
        super().__init__()
        self.reanalyze_callback = reanalyze_callback
        self.messages = messages
        self.user_name = user_name
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle model selection submission."""
        model = self.model_input.value.strip()
        
        await interaction.response.send_message(
            f"🔄 **Re-analyzing {self.user_name} with {model}...**\n"
            f"⏳ This may take a minute...",
            ephemeral=True
        )
        
        # Call the re-analysis callback
        try:
            await self.reanalyze_callback(interaction, model, self.messages, self.user_name)
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error during re-analysis: {str(e)}",
                ephemeral=True
            )


def generate_pdf_report(
    buffer: io.BytesIO,
    analysis_data: Dict[str, Any],
    user_name: str,
    message_count: int
) -> io.BytesIO:
    """
    Generate a beautifully formatted PDF report.
    
    Args:
        buffer: BytesIO buffer to write PDF to
        analysis_data: Structured analysis data
        user_name: Name of analyzed user
        message_count: Number of messages analyzed
    
    Returns:
        BytesIO buffer with PDF content
    """
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor='#2C3E50',
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor='#7F8C8D',
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor='#3498DB',
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=11,
        textColor='#2C3E50',
        spaceAfter=12,
        leading=16,
        alignment=TA_LEFT
    )
    
    # Title
    story.append(Paragraph(f"Comprehensive Analysis Report", title_style))
    story.append(Paragraph(f"{user_name}", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Metadata
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    story.append(Paragraph(f"Generated: {timestamp}", subtitle_style))
    story.append(Paragraph(f"Messages Analyzed: {message_count:,}", subtitle_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Sections
    sections = [
        ("📝 Overview", "overview"),
        ("💬 Communication Style", "communication_style"),
        ("✨ Personality Traits", "personality_traits"),
        ("🎯 Interests & Topics", "interests"),
        ("🔄 Behavioral Patterns", "behavioral_patterns"),
        ("⏰ Activity Patterns", "activity_patterns"),
        ("👥 Social Dynamics", "social_dynamics"),
        ("📚 Vocabulary & Expression", "vocabulary"),
        ("💡 Unique Insights", "unique_insights"),
    ]
    
    for section_title, section_key in sections:
        if section_key in analysis_data and analysis_data[section_key]:
            story.append(Paragraph(section_title, heading_style))
            
            # Clean and format the content
            content = analysis_data[section_key]
            # Remove markdown formatting for PDF
            content = content.replace('**', '').replace('*', '').replace('`', '')
            
            story.append(Paragraph(content, body_style))
            story.append(Spacer(1, 0.15*inch))
    
    # Build PDF
    doc.build(story)
    return buffer


def create_analysis_embeds(analysis_data: Dict[str, Any], user_name: str, message_count: int) -> List[discord.Embed]:
    """
    Create beautiful paginated embeds from analysis data.
    
    Args:
        analysis_data: Comprehensive analysis data
        user_name: Display name of analyzed user
        message_count: Number of messages analyzed
    
    Returns:
        List of formatted embed pages
    """
    pages = []
    
    # Page 1: Overview & Communication Style
    embed1 = discord.Embed(
        title=f"📊 Analysis: {user_name}",
        description=f"**Comprehensive personality and behavior analysis**\n*Based on {message_count:,} messages*",
        color=discord.Color.blue()
    )
    
    if "overview" in analysis_data:
        embed1.add_field(
            name="📝 Overview",
            value=analysis_data["overview"][:1024],
            inline=False
        )
    
    if "communication_style" in analysis_data:
        embed1.add_field(
            name="💬 Communication Style",
            value=analysis_data["communication_style"][:1024],
            inline=False
        )
    
    embed1.set_footer(text="Page 1 • Use buttons below to navigate")
    pages.append(embed1)
    
    # Page 2: Personality & Interests
    embed2 = discord.Embed(
        title=f"🎭 Personality Profile: {user_name}",
        color=discord.Color.green()
    )
    
    if "personality_traits" in analysis_data:
        embed2.add_field(
            name="✨ Personality Traits",
            value=analysis_data["personality_traits"][:1024],
            inline=False
        )
    
    if "interests" in analysis_data:
        embed2.add_field(
            name="🎯 Interests & Topics",
            value=analysis_data["interests"][:1024],
            inline=False
        )
    
    embed2.set_footer(text="Page 2 • Use buttons below to navigate")
    pages.append(embed2)
    
    # Page 3: Behavior & Activity
    embed3 = discord.Embed(
        title=f"📈 Behavioral Analysis: {user_name}",
        color=discord.Color.purple()
    )
    
    if "behavioral_patterns" in analysis_data:
        embed3.add_field(
            name="🔄 Behavioral Patterns",
            value=analysis_data["behavioral_patterns"][:1024],
            inline=False
        )
    
    if "activity_patterns" in analysis_data:
        embed3.add_field(
            name="⏰ Activity Patterns",
            value=analysis_data["activity_patterns"][:1024],
            inline=False
        )
    
    embed3.set_footer(text="Page 3 • Use buttons below to navigate")
    pages.append(embed3)
    
    # Page 4: Social Dynamics & Insights
    embed4 = discord.Embed(
        title=f"🤝 Social Dynamics: {user_name}",
        color=discord.Color.orange()
    )
    
    if "social_dynamics" in analysis_data:
        embed4.add_field(
            name="👥 Social Interactions",
            value=analysis_data["social_dynamics"][:1024],
            inline=False
        )
    
    if "unique_insights" in analysis_data:
        embed4.add_field(
            name="💡 Unique Insights",
            value=analysis_data["unique_insights"][:1024],
            inline=False
        )
    
    if "vocabulary" in analysis_data:
        embed4.add_field(
            name="📚 Vocabulary & Expression",
            value=analysis_data["vocabulary"][:1024],
            inline=False
        )
    
    # Add channel-specific insights if available
    if "channel_insights" in analysis_data and analysis_data["channel_insights"]:
        embed5 = discord.Embed(
            title=f"🎯 Channel-Specific Insights: {user_name}",
            description="*Behavior analysis in top 3 most active channels*",
            color=discord.Color.teal()
        )
        embed5.add_field(
            name="📍 Top Channels Analysis",
            value=analysis_data["channel_insights"][:4000],
            inline=False
        )
        embed5.set_footer(text="Page 5 • Channel-specific behavior patterns")
        pages.append(embed5)
    
    embed4.set_footer(text=f"Page 4 • Download PDF/TXT for complete details")
    pages.append(embed4)
    
    return pages


def format_full_report(analysis_data: Dict[str, Any], user_name: str, message_count: int) -> str:
    """
    Format complete analysis as downloadable text report.
    
    Args:
        analysis_data: Comprehensive analysis data
        user_name: Display name of analyzed user
        message_count: Number of messages analyzed
    
    Returns:
        Formatted text report
    """
    report = f"""
╔══════════════════════════════════════════════════════════════╗
║          COMPREHENSIVE USER ANALYSIS REPORT                  ║
╚══════════════════════════════════════════════════════════════╝

User: {user_name}
Messages Analyzed: {message_count:,}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

═══════════════════════════════════════════════════════════════

📝 OVERVIEW
───────────────────────────────────────────────────────────────
{analysis_data.get('overview', 'N/A')}

💬 COMMUNICATION STYLE
───────────────────────────────────────────────────────────────
{analysis_data.get('communication_style', 'N/A')}

✨ PERSONALITY TRAITS
───────────────────────────────────────────────────────────────
{analysis_data.get('personality_traits', 'N/A')}

🎯 INTERESTS & TOPICS
───────────────────────────────────────────────────────────────
{analysis_data.get('interests', 'N/A')}

🔄 BEHAVIORAL PATTERNS
───────────────────────────────────────────────────────────────
{analysis_data.get('behavioral_patterns', 'N/A')}

⏰ ACTIVITY PATTERNS
───────────────────────────────────────────────────────────────
{analysis_data.get('activity_patterns', 'N/A')}

👥 SOCIAL DYNAMICS
───────────────────────────────────────────────────────────────
{analysis_data.get('social_dynamics', 'N/A')}

📚 VOCABULARY & EXPRESSION
───────────────────────────────────────────────────────────────
{analysis_data.get('vocabulary', 'N/A')}

💡 UNIQUE INSIGHTS
───────────────────────────────────────────────────────────────
{analysis_data.get('unique_insights', 'N/A')}
"""
    
    # Add channel insights if available
    if "channel_insights" in analysis_data and analysis_data["channel_insights"]:
        report += f"""
🎯 CHANNEL-SPECIFIC INSIGHTS
───────────────────────────────────────────────────────────────
{analysis_data['channel_insights']}
"""
    
    report += """
═══════════════════════════════════════════════════════════════
End of Report
═══════════════════════════════════════════════════════════════
"""
    return report

