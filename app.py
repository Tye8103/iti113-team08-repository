import json
from pathlib import Path

import boto3
import streamlit as st


# CONFIGURATION


AWS_REGION = "ap-southeast-1"

# SageMaker endpoint is discovered automatically.
# No endpoint name needs to be entered in the Streamlit UI.
ENDPOINT_PREFIX = "sgp-rental-price-endpoint"

BASE_DIR=Path.cwd()
ZONE_MAP_IMAGE = BASE_DIR / "singapore_rental_zones.png"
RENT_CHART_IMAGE = BASE_DIR / "median_rent_by_district.png"



# SAGEMAKER CLIENTS


sagemaker = boto3.client(
    "sagemaker",
    region_name=AWS_REGION,
)

runtime = boto3.client(
    "sagemaker-runtime",
    region_name=AWS_REGION,
)


def get_sagemaker_endpoint():
    """Find the newest InService rental endpoint automatically."""

    endpoints = []
    next_token = None

    while True:
        kwargs = {
            "StatusEquals": "InService",
            "MaxResults": 100,
        }

        if next_token:
            kwargs["NextToken"] = next_token

        response = sagemaker.list_endpoints(**kwargs)
        endpoints.extend(response.get("Endpoints", []))

        next_token = response.get("NextToken")
        if not next_token:
            break

    matching = [
        endpoint
        for endpoint in endpoints
        if endpoint.get("EndpointName", "").lower().startswith(
            ENDPOINT_PREFIX.lower()
        )
    ]

    if not matching:
        raise RuntimeError(
            f"No InService SageMaker endpoint found with prefix "
            f"'{ENDPOINT_PREFIX}'."
        )

    # Use the most recently created matching endpoint.
    matching.sort(
        key=lambda x: x.get("CreationTime"),
        reverse=True,
    )

    return matching[0]["EndpointName"]


# Discover the endpoint once when the Streamlit session starts.
try:
    ENDPOINT_NAME = get_sagemaker_endpoint()
    ENDPOINT_ERROR = None
except Exception as exc:
    ENDPOINT_NAME = None
    ENDPOINT_ERROR = str(exc)




# PAGE CONFIGURATION


st.set_page_config(
    page_title="My Rent & Investment Estimator",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)



# CUSTOM CSS


st.markdown(
    """
    <style>

    /* Main page */
    .block-container {
        max-width: 1400px;
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    /* Header */
    .app-header {
        background: linear-gradient(135deg, #0b2a6f, #124ea2);
        color: white;
        padding: 1.35rem 1.5rem;
        border-radius: 14px;
        margin-bottom: 1.2rem;
        text-align: center;
        box-shadow: 0 4px 14px rgba(0,0,0,0.12);
    }

    .app-header h1 {
        margin: 0;
        font-size: 2.15rem;
        font-weight: 700;
    }

    .app-header p {
        margin: 0.45rem 0 0 0;
        font-size: 1.02rem;
        opacity: 0.95;
    }

    /* Input / information boxes */
    .section-box {
        border: 1px solid #d7e2f2;
        border-radius: 12px;
        padding: 1.0rem 1.15rem 1.15rem 1.15rem;
        background: #fbfdff;
        min-height: 100%;
    }

    .section-title {
        font-size: 1.25rem;
        font-weight: 700;
        margin-bottom: 0.8rem;
    }

    .info-title {
        color: #2f7d3c;
    }

    /* Results */
    .results-box {
        border: 1px solid #ead9a6;
        border-radius: 12px;
        padding: 1rem 1rem 0.85rem 1rem;
        background: #fffdf5;
        margin-top: 1.2rem;
    }

    .results-title {
        text-align: center;
        color: #c56b0a;
        font-size: 1.35rem;
        font-weight: 700;
        margin-bottom: 0.7rem;
    }

    .metric-card {
        background: white;
        border: 1px solid #e2e5ea;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
        min-height: 125px;
    }

    .metric-label {
        font-size: 0.95rem;
        font-weight: 600;
        color: #333333;
        margin-bottom: 0.35rem;
    }

    .metric-value {
        font-size: 1.65rem;
        font-weight: 750;
    }

    .monthly {
        color: #21833b;
    }

    .annual {
        color: #124ea2;
    }

    .investment {
        color: #7b28a8;
    }

    .disclaimer {
        background: #f8f8f8;
        border-radius: 8px;
        padding: 0.6rem 0.8rem;
        margin-top: 0.8rem;
        font-size: 0.82rem;
        color: #555555;
    }

    /* Resource links */
    .resource-note {
        font-size: 0.9rem;
        color: #555555;
    }

    /* Buttons */
    div.stButton > button {
        border-radius: 8px;
        font-weight: 650;
        min-height: 2.7rem;
    }

    </style>
    """,
    unsafe_allow_html=True,
)



# HEADER


st.markdown(
    """
    <div class="app-header">
        <h1>🏢 My Rent & Investment Estimator</h1>
        <p>
            Estimate monthly rental income and indicative investment
            value of a rental property.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)



# MODEL FEATURES


DISTRICTS = [
    1, 2, 3, 4, 5, 6, 7, 8, 9,
    10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
    20, 21, 22, 23, 25, 26, 27, 28,
]

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]



# SESSION STATE


DEFAULTS = {
    "bedroom": 3,
    "area_sm": 90,
    "lease_year": 2024,
    "lease_month": 6,
    "district": 5,
    "interest_rate": 4.0,
    "run_prediction": False,
    "prediction_result": None,
    "request_payload": None,
    "raw_response": None,
    "prediction_error": None,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Streamlit forbids setting st.session_state[key] for a widget's key
# after that widget has already been instantiated in the current run.
# clear_all_filters() used to do that directly, which crashed because
# it was called from a button below the input widgets. Instead, the
# button just raises this flag and reruns; the actual reset happens
# here, at the top of the script, before any widget with these keys
# is created.
if st.session_state.get("_reset_requested", False):
    for key, value in DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["_reset_requested"] = False


def clear_all_filters():
    """Request a reset of all user inputs and prediction results.

    Does not touch st.session_state directly -- see the flag check
    above for why. Call this, then st.rerun().
    """
    st.session_state["_reset_requested"] = True



# HELPER FUNCTIONS


def extract_prediction(result):
    """
    Extract the predicted rental value from common JSON response
    formats returned by the SageMaker V2 inference script.
    """

    if isinstance(result, list):

        if not result:
            raise ValueError("The SageMaker response list is empty.")

        return float(result[0])

    if isinstance(result, dict):

        if "predictions" in result:

            predictions = result["predictions"]

            if isinstance(predictions, list):

                if not predictions:
                    raise ValueError(
                        "The 'predictions' list is empty."
                    )

                return float(predictions[0])

            return float(predictions)

        if "prediction" in result:
            return float(result["prediction"])

        if "predicted_rent" in result:
            return float(result["predicted_rent"])

        if "predicted_rental" in result:
            return float(result["predicted_rental"])

        raise ValueError(
            "Unexpected model response dictionary: "
            f"{result}"
        )

    return float(result)


def compact_currency(value):
    """Format large currency values as S$1.14M / S$950K."""
    value = float(value)

    if abs(value) >= 1_000_000:
        return f"S${value / 1_000_000:.2f}M"

    if abs(value) >= 1_000:
        return f"S${value / 1_000:.1f}K"

    return f"S${value:,.0f}"


def run_sagemaker_prediction():
    """Send the five model features to the SageMaker V2 endpoint."""

    payload = {
        "bedroom": int(st.session_state["bedroom"]),
        "area_sm": int(st.session_state["area_sm"]),
        "lease_year": int(st.session_state["lease_year"]),
        "lease_month": int(st.session_state["lease_month"]),
        "district": int(st.session_state["district"]),
    }
    response = runtime.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Accept="application/json",
        Body=json.dumps(payload),
    )

    response_body = (
        response["Body"]
        .read()
        .decode("utf-8")
    )

    result = json.loads(response_body)

    predicted_rent = extract_prediction(result)

    if predicted_rent < 0:
        raise ValueError(
            f"The model returned a negative rental value: "
            f"{predicted_rent}"
        )

    annual_rent = predicted_rent * 12

    required_yield = float(
        st.session_state["interest_rate"]
    ) / 100

    if required_yield <= 0:
        raise ValueError(
            "Required rental yield must be greater than zero."
        )

    investment_value = annual_rent / required_yield

    st.session_state["prediction_result"] = {
        "monthly_rent": predicted_rent,
        "annual_rent": annual_rent,
        "investment_value": investment_value,
        "yield": float(st.session_state["interest_rate"]),
    }

    st.session_state["request_payload"] = payload
    st.session_state["raw_response"] = response_body
    st.session_state["prediction_error"] = None



# MAIN TWO-COLUMN AREA


left_col, right_col = st.columns(
    [1, 1.15],
    gap="large",
)



# LEFT — PROPERTY VARIABLE INPUT


with left_col:

    st.markdown(
        '<div class="section-title">🏠 PROPERTY INPUT</div>',
        unsafe_allow_html=True,
    )

    st.number_input(
        "Bedrooms",
        min_value=1,
        max_value=10,
        step=1,
        key="bedroom",
    )

    st.number_input(
        "Floor Area (sqm)",
        min_value=20,
        max_value=500,
        step=1,
        key="area_sm",
    )

    st.number_input(
        "Lease Year",
        min_value=1990,
        max_value=2030,
        step=1,
        key="lease_year",
    )

    st.selectbox(
        "Lease Month",
        options=list(range(1, 13)),
        format_func=lambda x: MONTHS[x - 1],
        key="lease_month",
    )

    st.selectbox(
        "District",
        options=DISTRICTS,
        format_func=lambda x: f"District {x}",
        key="district",
    )

    st.number_input(
        "Required Yield (%)",
        min_value=1.0,
        max_value=15.0,
        step=0.25,
        format="%.2f",
        key="interest_rate",
    )

    st.caption(
        "Example: 4% means annual rental income ÷ 4%."
    )

    
    # BUTTONS
    

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button(
        "🔄 Update Results",
        type="primary",
        width="stretch",
    ):

        if ENDPOINT_NAME is None:
            st.session_state["prediction_error"] = (
                "No SageMaker endpoint could be found automatically "
                f"(prefix '{ENDPOINT_PREFIX}'). "
                f"Details: {ENDPOINT_ERROR}"
            )
            st.session_state["run_prediction"] = False
            st.session_state["prediction_result"] = None

        else:

            st.session_state["run_prediction"] = True

            try:

                with st.spinner(
                    "Requesting prediction from SageMaker..."
                ):
                    run_sagemaker_prediction()

            except Exception as exc:

                st.session_state["prediction_result"] = None
                st.session_state["prediction_error"] = str(exc)

    # ERROR MESSAGE


    if st.session_state.get("prediction_error"):

        st.error(
            "Unable to obtain prediction from the "
            "SageMaker V2 endpoint."
        )

        with st.expander("View error details"):

            st.code(
                st.session_state["prediction_error"]
            )



    # RESULTS


    prediction = st.session_state.get("prediction_result")


    if prediction is not None:

        st.markdown(
            """
            <div class="results-box">
                <div class="results-title">
                    📊 RESULTS
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        result_col1, result_col2, result_col3 = st.columns(3)

        with result_col1:

            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">
                        Monthly Rent
                    </div>
                    <div class="metric-value monthly">
                        S${prediction["monthly_rent"]:,.0f}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with result_col2:

            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">
                        Annual Rent
                    </div>
                    <div class="metric-value annual">
                        S${prediction["annual_rent"]:,.0f}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with result_col3:

            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">
                        Indicative Investment Value
                        ({prediction["yield"]:.2f}% Yield)
                    </div>
                    <div class="metric-value investment">
                        {compact_currency(prediction["investment_value"])}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            """
            <div class="disclaimer">
                ℹ️ Results are estimates generated by the machine-learning
                model based on the supplied property information. Actual
                rental rates and market values may differ.
            </div>
            """,
            unsafe_allow_html=True,
        )

   
        # VALUATION CALCULATION
    

        with st.expander("🧮 View valuation calculation"):

            monthly = prediction["monthly_rent"]
            annual = prediction["annual_rent"]
            yield_percent = prediction["yield"]
            yield_decimal = yield_percent / 100
            value = prediction["investment_value"]

            st.write(
                f"**Monthly rent:** S${monthly:,.0f}"
            )

            st.write(
                f"**Annual rent:** "
                f"S${monthly:,.0f} × 12 = "
                f"S${annual:,.0f}"
            )

            st.write(
                f"**Required rental yield:** "
                f"{yield_percent:.2f}% "
                f"({yield_decimal:.4f})"
            )

            st.write(
                f"**Investment value:** "
                f"S${annual:,.0f} ÷ {yield_decimal:.4f}"
            )

            st.write(
                f"### Indicative value: "
                f"S${value:,.0f}"
            )

   
        # SAGEMAKER ENDPOINT REQUEST
   

        with st.expander("📤 View request sent to SageMaker"):

            st.json(
                st.session_state["request_payload"]
            )

    
        # SAGEMAKER ENDPOINT RESPONSE
   

        with st.expander("📥 View SageMaker response"):

            st.code(
                st.session_state["raw_response"],
                language="json",
            )




    if st.button(
        "🗑️ Clear All Filters",
        width="stretch",
    ):
        clear_all_filters()
        st.rerun()



# RIGHT — PROPERTY INFORMATION


with right_col:

    st.markdown(
        '<div class="section-title info-title">'
        'ℹ️ PROPERTY INFORMATION'
        '</div>',
        unsafe_allow_html=True,
    )

    
    # RENTAL ZONE MAP
   

    st.markdown(
        "### Singapore Private Residential Rental Zones"
    )

    if ZONE_MAP_IMAGE.exists():

        st.image(
            str(ZONE_MAP_IMAGE),
            width="content",
        )

    else:

        st.warning(
            "Singapore rental-zone map not found. "
            "Place singapore_rental_zones.png in the "
            "same folder as app.py."
        )

    st.caption(
        "The map shows Singapore's private residential "
        "rental zones used for district-based rental analysis."
    )

   
    # MEDIAN RENT CHART
    

    st.markdown(
        "### 📊 Median Monthly Rent by District"
    )

    if RENT_CHART_IMAGE.exists():

        st.image(
            str(RENT_CHART_IMAGE),
            width="content",
        )

    else:

        st.warning(
            "Median rent chart not found. "
            "Place median_rent_by_district.png in the "
            "same folder as app.py."
        )

   
    # PUBLIC INFORMATION AND RESOURCES
    

    st.markdown("### 🔗 Official Resources")

    st.link_button(
        "URA – Urban Redevelopment Authority",
        "https://www.ura.gov.sg/",
         width="content",
    )

    st.link_button(
        "URA – Property Market Information",
        "https://eservice.ura.gov.sg/property-market-information/pmiResidentialRentalSearch",
        width="content",
    )

    st.link_button(
        "URA – Property Rental",
        "https://www.ura.gov.sg/guidelines/property-and-business-owners/property/renting-property/",
        width="content",
    )

    st.markdown(
        '<p class="resource-note">'
        "Public resources are provided for reference. "
        "The rental estimate itself is produced by the "
        "machine-learning model."
        "</p>",
        unsafe_allow_html=True,
    )



# ABOUT THE MODEL


with st.expander("🤖 About the Model"):

    st.markdown(
        """
        ### How the model works

        The rental estimate is generated by a machine-learning
        regression model trained using historical Singapore rental
        data for non-landed properties.

        The model uses property characteristics to estimate the
        property's monthly rental value.

        ### Model inputs

        The current V2 model accepts these five features:

        1. **Number of bedrooms**
        2. **Floor area (sqm)**
        3. **Lease year**
        4. **Lease month**
        5. **Singapore district**

        ### Prediction flow

        **Property Information → SageMaker Endpoint → "
        "XGBoost Model → Estimated Monthly Rent**

        The estimated monthly rental income is multiplied by 12
        to calculate annual rental income.

        The application then calculates an indicative investment
        value using the selected required rental yield:

        **Investment Value = Annual Rental Income ÷ Required Rental Yield**

        ### Important note

        The investment value is an analytical estimate based on
        the rental income predicted by the model and the yield
        assumption selected by the user.

        It should not be interpreted as an official property
        valuation, guaranteed rental income, or investment advice.
        """
    )

    st.markdown("### SageMaker architecture")

    st.code(
        """
User
  │
  ▼
Streamlit Application
  │
  │ JSON
  ▼
SageMaker Runtime
  │
  ▼
SageMaker V2 Endpoint
  │
  ▼
XGBoost Regression Model
  │
  ▼
Predicted Monthly Rent
  │
  ├── × 12
  │
  ▼
Annual Rental Income
  │
  ├── ÷ Required Rental Yield
  │
  ▼
Indicative Investment Value
        """,
        language="text",
    )

    st.markdown("### Model limitations")

    st.markdown(
        """
        - The prediction depends on the quality and coverage of
          the historical training data.
        - Actual rental prices can differ from model predictions.
        - Property condition, exact location, furnishing,
          amenities, floor level, view, and other factors may not
          be fully represented by the five model inputs.
        - The indicative investment value depends directly on the
          required rental-yield assumption.
        """
    )
