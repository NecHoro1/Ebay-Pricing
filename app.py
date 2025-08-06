import streamlit as st
import pandas as pd
import io
import plotly.express as px

# Initialize session state for storing listings and undo buffer
if 'listings' not in st.session_state:
    st.session_state['listings'] = {}
if 'undo_buffer' not in st.session_state:
    st.session_state['undo_buffer'] = []

st.set_page_config(layout="wide")
st.title("eBay Pricing Dashboard")

# --- Top Control Panel ---
st.sidebar.header("Controls")

# Search Product (moved to top)
search_term = st.text_input("Search SKU")

# Import CSV
uploaded_file = st.sidebar.file_uploader("Upload CSV", type="csv")
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    grouped = df[df["Seller's Name"].notna()].groupby(df['SKU'].ffill())
    for sku, group in grouped:
        if sku not in st.session_state['listings']:
            my_listing = df[(df['SKU'] == sku) & (df["Seller's Name"].isna())].iloc[0]
            st.session_state['listings'][sku] = {
                'my_price': float(str(my_listing['Listed Price']).replace('$', '').replace(',', '')),
                'my_shipping': float(str(my_listing['BUYER Shipping Cost']).replace('$', '').replace(',', '')),
                'competitors': []
            }
        for _, row in group.iterrows():
            st.session_state['listings'][sku]['competitors'].append({
                'seller': row["Seller's Name"],
                'price': float(str(row['Listed Price']).replace('$', '').replace(',', '')),
                'shipping': float(str(row['BUYER Shipping Cost']).replace('$', '').replace(',', ''))
            })
    st.sidebar.success("CSV imported!")

# Add New Product
st.sidebar.subheader("Add Product")
with st.sidebar.form("add_product_form"):
    sku = st.text_input("SKU")
    my_price = st.number_input("Listed Price", min_value=0.0, step=0.01)
    my_shipping = st.number_input("Shipping Cost", min_value=0.0, step=0.01)
    comp_sellers = st.text_area("Competitor Sellers (one per line)")
    comp_prices = st.text_area("Competitor Prices (one per line)")
    comp_shipping = st.text_area("Competitor Shipping (one per line)")
    submitted = st.form_submit_button("Add")
    if submitted and sku:
        comps = []
        sellers = comp_sellers.strip().splitlines()
        prices = comp_prices.strip().splitlines()
        shipping = comp_shipping.strip().splitlines()
        for s, p, sh in zip(sellers, prices, shipping):
            try:
                comps.append({
                    'seller': s,
                    'price': float(p.replace("$", "")),
                    'shipping': float(sh.replace("$", ""))
                })
            except:
                continue
        st.session_state['listings'][sku] = {
            'my_price': my_price,
            'my_shipping': my_shipping,
            'competitors': comps
        }
        st.sidebar.success(f"Added {sku} with {len(comps)} competitors")

# Overpriced Filter
overpriced_only = st.sidebar.checkbox("Only show overpriced")

# Export CSV
if st.sidebar.button("Export CSV"):
    all_data = []
    for sku, data in st.session_state['listings'].items():
        all_data.append({
            'SKU': sku,
            'Seller': 'You',
            'Price': data['my_price'],
            'Shipping': data['my_shipping'],
            'Total': data['my_price'] + data['my_shipping']
        })
        for comp in data['competitors']:
            total = comp['price'] + comp['shipping']
            all_data.append({
                'SKU': sku,
                'Seller': comp['seller'],
                'Price': comp['price'],
                'Shipping': comp['shipping'],
                'Total': total
            })
    export_df = pd.DataFrame(all_data)
    st.sidebar.download_button("Download CSV", export_df.to_csv(index=False).encode('utf-8'), "all_listings.csv", "text/csv")

# --- Dashboard ---
st.header("Product Dashboard")
for sku, data in st.session_state['listings'].items():
    if search_term and search_term.lower() not in sku.lower():
        continue

    with st.expander(f"SKU: {sku}", expanded=True):
        my_total = data['my_price'] + data['my_shipping']
        competitors = data['competitors']
        if competitors:
            comp_totals = [c['price'] + c['shipping'] for c in competitors]
            min_price = min(comp_totals)
            if overpriced_only and not (my_total > min_price * 1.1):
                continue

        st.markdown(f"<div style='margin-bottom:10px'><strong>Your Total Price:</strong> <span style='color:#2c7be5;'>${my_total:.2f}</span> &nbsp; <small>(Price: ${data['my_price']}, Shipping: ${data['my_shipping']})</small></div>", unsafe_allow_html=True)

        if competitors:
            avg_price = sum(comp_totals) / len(comp_totals)
            min_price = min(comp_totals)
            max_price = max(comp_totals)

            st.markdown(f"<div style='margin-bottom:10px'><strong>Competitor Stats:</strong><br>", unsafe_allow_html=True)
            st.markdown(f"<ul style='margin-left: 20px;'>"
                        f"<li><strong>Average:</strong> ${avg_price:.2f}</li>"
                        f"<li><strong>Lowest:</strong> ${min_price:.2f}</li>"
                        f"<li><strong>Highest:</strong> ${max_price:.2f}</li>"
                        f"</ul></div>", unsafe_allow_html=True)

            comp_df = pd.DataFrame(data['competitors'])
            edited_df = st.data_editor(comp_df, num_rows="dynamic", use_container_width=True)
            st.session_state['listings'][sku]['competitors'] = edited_df.to_dict('records')

            if st.session_state['undo_buffer']:
                if st.button("Undo Last Delete"):
                    last_sku, last_entry = st.session_state['undo_buffer'].pop()
                    st.session_state['listings'][last_sku]['competitors'].append(last_entry)
                    st.experimental_rerun()

            # --- Bar Chart ---
            chart_df = pd.DataFrame([{ 'seller': c['seller'], 'total': c['price'] + c['shipping'] } for c in data['competitors']])
            chart_df = pd.concat([chart_df, pd.DataFrame([{'seller': 'You', 'total': my_total}])], ignore_index=True)
            chart_df = chart_df.drop_duplicates(subset=['seller', 'total'])
            chart_df = chart_df.sort_values(by='total')
            chart_df['color'] = chart_df['seller'].apply(lambda x: '#2c7be5' if x == 'You' else '#888888')
            chart_df['total_label'] = chart_df['total'].apply(lambda x: f"${x:.2f}")
            bar_fig = px.bar(chart_df, x='seller', y='total', title='Total Price Comparison', text='total_label', color='color', color_discrete_map='identity')
            bar_fig.update_traces(textposition='outside', marker_line_color='black')
            st.plotly_chart(bar_fig)

            # --- Smart Suggestions ---
            if my_total < min_price:
                st.success("✅ You are the lowest priced!")
            elif my_total > max_price:
                st.error("❌ You are the highest priced!")
            else:
                st.warning("⚠️ You are mid-range in pricing.")

            if my_total > min_price * 1.1:
                st.info(f"📉 Suggestion: Lower price by ${my_total - min_price:.2f} to be most competitive.")
        else:
            st.info("No competitor data added yet.")
