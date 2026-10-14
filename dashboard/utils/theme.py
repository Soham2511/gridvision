"""Brand design system, color palette, and CSS injection for GridVision (Light Mode)."""

from __future__ import annotations

import streamlit as st

# Authoritative Color Palette
COLOR_MIDNIGHT_NAVY = "#0B1F33"
COLOR_SMART_TEAL = "#00B8A9"
COLOR_ELECTRIC_CYAN = "#21C7D9"
COLOR_GRID_BLUE = "#087EBD"
COLOR_ENERGY_AMBER = "#FFC247"
COLOR_PURE_WHITE = "#FFFFFF"

# Semantic & Theme Tokens (Light Mode)
COLOR_BG = "#FFFFFF"
COLOR_SURFACE_CARD = "#FFFFFF"
COLOR_TEXT_PRIMARY = "#0B1F33"
COLOR_TEXT_MUTED = "rgba(11, 31, 51, 0.65)"
COLOR_BORDER = "rgba(8, 126, 189, 0.20)"
COLOR_SUCCESS = "#00B8A9"
COLOR_WARNING = "#FFC247"
COLOR_DANGER = "#FFC247"
COLOR_INFO = "#087EBD"


def apply_custom_theme() -> None:
    """Inject premium, minimalist light-mode CSS styling into Streamlit."""
    css = f"""
    <style>
        /* Base typography & page backgrounds */
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
        
        html, body, [class*="css"] {{
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: {COLOR_TEXT_PRIMARY};
            background-color: {COLOR_BG};
        }}
        
        .stApp {{
            background: #FFFFFF;
        }}
        
        /* Sidebar styling */
        section[data-testid="stSidebar"] {{
            background-color: #FFFFFF !important;
            border-right: 1px solid rgba(8, 126, 189, 0.18) !important;
        }}
        
        section[data-testid="stSidebar"] div.block-container {{
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }}

        /* Hide default Streamlit multipage list so custom branded workspace navigation is used */
        [data-testid="stSidebarNav"] {{
            display: none !important;
        }}

        section[data-testid="stSidebar"] * {{
            color: {COLOR_TEXT_PRIMARY};
        }}

        /* Sidebar Tab Navigation Buttons */
        section[data-testid="stSidebar"] div.stButton > button {{
            text-align: left !important;
            justify-content: flex-start !important;
            padding: 0.55rem 0.85rem !important;
            font-size: 0.88rem !important;
            font-weight: 500 !important;
            border-radius: 6px !important;
            margin-bottom: 0.3rem !important;
            transition: all 0.15s ease-in-out !important;
        }}

        /* Active Tab in Sidebar */
        section[data-testid="stSidebar"] div.stButton > button[kind="primary"] {{
            background-color: #00B8A9 !important;
            color: #FFFFFF !important;
            border: 1px solid #00B8A9 !important;
            font-weight: 600 !important;
            box-shadow: 0 2px 6px rgba(0, 184, 169, 0.25) !important;
        }}

        /* Inactive Tab in Sidebar */
        section[data-testid="stSidebar"] div.stButton > button[kind="secondary"] {{
            background-color: #FFFFFF !important;
            color: #0B1F33 !important;
            border: 1px solid rgba(8, 126, 189, 0.18) !important;
            box-shadow: 0 1px 3px rgba(11, 31, 51, 0.03) !important;
        }}

        section[data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover {{
            background-color: rgba(8, 126, 189, 0.06) !important;
            color: #087EBD !important;
            border-color: #087EBD !important;
        }}
        
        /* Minimalist Metric Cards */
        .gv-kpi-card {{
            background: #FFFFFF;
            border: 1px solid {COLOR_BORDER};
            border-radius: 8px;
            padding: 1.1rem 1.25rem;
            box-shadow: 0 2px 10px rgba(11, 31, 51, 0.05);
            margin-bottom: 0.75rem;
            transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
        }}
        
        .gv-kpi-card:hover {{
            border-color: {COLOR_SMART_TEAL};
            box-shadow: 0 4px 16px rgba(0, 184, 169, 0.12);
            transform: translateY(-1px);
        }}
        
        .gv-kpi-label {{
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: {COLOR_TEXT_MUTED};
            margin-bottom: 0.35rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .gv-kpi-value {{
            font-size: 1.65rem;
            font-weight: 700;
            color: {COLOR_TEXT_PRIMARY};
            letter-spacing: -0.02em;
            line-height: 1.2;
        }}
        
        .gv-kpi-subtext {{
            font-size: 0.75rem;
            color: {COLOR_TEXT_MUTED};
            margin-top: 0.4rem;
        }}
        
        .gv-delta-pos {{
            color: {COLOR_SUCCESS};
            font-weight: 600;
            font-size: 0.8rem;
        }}
        
        .gv-delta-neg {{
            color: {COLOR_GRID_BLUE};
            font-weight: 600;
            font-size: 0.8rem;
        }}

        /* Header Bar */
        .gv-header-container {{
            background: #FFFFFF;
            border: 1px solid {COLOR_BORDER};
            padding: 0.75rem 1rem;
            margin-bottom: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(11, 31, 51, 0.04);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        /* Persona Selection Cards on Landing Page */
        .gv-persona-card {{
            background: #FFFFFF;
            border: 1px solid {COLOR_BORDER};
            border-radius: 10px;
            padding: 1.75rem 1.5rem;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: 0 4px 16px rgba(11, 31, 51, 0.06);
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        
        .gv-persona-card:hover {{
            border-color: {COLOR_SMART_TEAL};
            box-shadow: 0 8px 24px rgba(0, 184, 169, 0.15);
            transform: translateY(-3px);
        }}

        /* Badges & Pills */
        .gv-badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}
        
        .gv-badge-cyan {{
            background: rgba(33, 199, 217, 0.14);
            color: {COLOR_GRID_BLUE};
            border: 1px solid rgba(33, 199, 217, 0.4);
        }}
        
        .gv-badge-amber {{
            background: rgba(255, 194, 71, 0.18);
            color: {COLOR_MIDNIGHT_NAVY};
            border: 1px solid rgba(255, 194, 71, 0.5);
        }}
        
        .gv-badge-teal {{
            background: rgba(0, 184, 169, 0.12);
            color: {COLOR_SMART_TEAL};
            border: 1px solid rgba(0, 184, 169, 0.4);
        }}

        /* Button Styling Overrides */
        div.stButton > button {{
            background: rgba(8, 126, 189, 0.08) !important;
            color: {COLOR_TEXT_PRIMARY} !important;
            border: 1px solid rgba(8, 126, 189, 0.3) !important;
            border-radius: 6px !important;
            padding: 0.45rem 1.25rem !important;
            font-weight: 600 !important;
            transition: all 0.15s ease !important;
        }}
        
        div.stButton > button:hover {{
            background: {COLOR_SMART_TEAL} !important;
            color: {COLOR_PURE_WHITE} !important;
            border-color: {COLOR_SMART_TEAL} !important;
            box-shadow: 0 4px 14px rgba(0, 184, 169, 0.25) !important;
        }}
        
        div.stButton > button:active {{
            transform: scale(0.98);
        }}

        /* Form Controls & Inputs */
        .stSelectbox div[data-baseweb="select"] > div {{
            background-color: #FFFFFF !important;
            border: 1px solid {COLOR_BORDER} !important;
            border-radius: 6px !important;
            color: {COLOR_TEXT_PRIMARY} !important;
        }}

        /* Drawer / Alerts Panel */
        .gv-alert-item {{
            background: #FFFFFF;
            border-left: 3px solid {COLOR_GRID_BLUE};
            border-top: 1px solid {COLOR_BORDER};
            border-right: 1px solid {COLOR_BORDER};
            border-bottom: 1px solid {COLOR_BORDER};
            padding: 0.85rem 1rem;
            border-radius: 4px;
            margin-bottom: 0.65rem;
            box-shadow: 0 2px 6px rgba(11, 31, 51, 0.04);
        }}
        
        .gv-alert-critical {{
            border-left-color: {COLOR_DANGER} !important;
        }}
        
        .gv-alert-warning {{
            border-left-color: {COLOR_WARNING} !important;
        }}
        
        .gv-alert-info {{
            border-left-color: {COLOR_INFO} !important;
        }}
        
        /* Clean tabs styling */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 8px;
            background-color: rgba(11, 31, 51, 0.03);
            padding: 4px;
            border-radius: 8px;
            border: 1px solid rgba(8, 126, 189, 0.15);
        }}
        
        .stTabs [data-baseweb="tab"] {{
            border-radius: 6px;
            color: {COLOR_TEXT_MUTED} !important;
            padding: 8px 16px;
            font-weight: 500;
        }}
        
        .stTabs [aria-selected="true"] {{
            background-color: #FFFFFF !important;
            color: {COLOR_TEXT_PRIMARY} !important;
            border: 1px solid rgba(0, 184, 169, 0.45) !important;
            box-shadow: 0 2px 6px rgba(11, 31, 51, 0.06);
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
