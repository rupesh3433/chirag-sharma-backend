@echo off
setlocal enabledelayedexpansion

echo ============================================
echo Creating Agent Folder Structure...
echo ============================================

REM Root Agent Folder
mkdir agent

REM -------------------------------
REM bootstrap
REM -------------------------------
mkdir agent\bootstrap
type nul > agent\bootstrap\__init__.py
type nul > agent\bootstrap\container.py
type nul > agent\bootstrap\loader.py
type nul > agent\bootstrap\registry.py

REM -------------------------------
REM api
REM -------------------------------
mkdir agent\api
type nul > agent\api\__init__.py
type nul > agent\api\router.py
type nul > agent\api\request_schema.py
type nul > agent\api\response_schema.py
type nul > agent\api\error_handler.py

REM -------------------------------
REM conversation
REM -------------------------------
mkdir agent\conversation
type nul > agent\conversation\__init__.py
type nul > agent\conversation\session.py
type nul > agent\conversation\session_manager.py
type nul > agent\conversation\history.py
type nul > agent\conversation\turn.py

REM -------------------------------
REM pipeline
REM -------------------------------
mkdir agent\pipeline
type nul > agent\pipeline\__init__.py
type nul > agent\pipeline\orchestrator.py
type nul > agent\pipeline\stage_preprocess.py
type nul > agent\pipeline\stage_intent.py
type nul > agent\pipeline\stage_entities.py
type nul > agent\pipeline\stage_belief_update.py
type nul > agent\pipeline\stage_policy.py
type nul > agent\pipeline\stage_booking.py
type nul > agent\pipeline\stage_response.py

REM -------------------------------
REM nlp
REM -------------------------------
mkdir agent\nlp
type nul > agent\nlp\__init__.py
type nul > agent\nlp\tokenizer.py
type nul > agent\nlp\normalizer.py
type nul > agent\nlp\intent_detector.py
type nul > agent\nlp\entity_package.py
type nul > agent\nlp\entity_date.py
type nul > agent\nlp\entity_phone.py
type nul > agent\nlp\entity_address.py

REM -------------------------------
REM embeddings
REM -------------------------------
mkdir agent\embeddings
type nul > agent\embeddings\__init__.py
type nul > agent\embeddings\model_loader.py
type nul > agent\embeddings\encoder.py
type nul > agent\embeddings\similarity.py
type nul > agent\embeddings\service_index.py
type nul > agent\embeddings\intent_prototypes.py

REM -------------------------------
REM domain
REM -------------------------------
mkdir agent\domain
type nul > agent\domain\__init__.py

mkdir agent\domain\slots
type nul > agent\domain\slots\__init__.py
type nul > agent\domain\slots\base_slot.py

mkdir agent\domain\cart
type nul > agent\domain\cart\__init__.py
type nul > agent\domain\cart\cart.py
type nul > agent\domain\cart\cart_item.py

mkdir agent\domain\pricing
type nul > agent\domain\pricing\__init__.py
type nul > agent\domain\pricing\discount_rules.py
type nul > agent\domain\pricing\discount_calculator.py

mkdir agent\domain\belief
type nul > agent\domain\belief\__init__.py
type nul > agent\domain\belief\belief_graph.py

mkdir agent\domain\policies
type nul > agent\domain\policies\__init__.py
type nul > agent\domain\policies\transition_rules.py

REM -------------------------------
REM services
REM -------------------------------
mkdir agent\services
type nul > agent\services\__init__.py
type nul > agent\services\services_catalog.py

REM -------------------------------
REM booking
REM -------------------------------
mkdir agent\booking
type nul > agent\booking\__init__.py
type nul > agent\booking\booking_mapper.py
type nul > agent\booking\booking_request_sender.py
type nul > agent\booking\otp_verifier.py
type nul > agent\booking\booking_state.py

REM -------------------------------
REM knowledge
REM -------------------------------
mkdir agent\knowledge
type nul > agent\knowledge\__init__.py
type nul > agent\knowledge\knowledge_retriever.py

REM -------------------------------
REM response
REM -------------------------------
mkdir agent\response
type nul > agent\response\__init__.py
type nul > agent\response\message_builder.py
type nul > agent\response\summary_builder.py
type nul > agent\response\pricing_builder.py
type nul > agent\response\clarification_builder.py

REM -------------------------------
REM validation
REM -------------------------------
mkdir agent\validation
type nul > agent\validation\__init__.py
type nul > agent\validation\phone_validator.py
type nul > agent\validation\date_validator.py
type nul > agent\validation\address_validator.py
type nul > agent\validation\confirmation_validator.py

REM -------------------------------
REM utils
REM -------------------------------
mkdir agent\utils
type nul > agent\utils\__init__.py
type nul > agent\utils\id_generator.py
type nul > agent\utils\time_utils.py
type nul > agent\utils\logger.py
type nul > agent\utils\safe_update.py

REM -------------------------------
REM config
REM -------------------------------
mkdir agent\config
type nul > agent\config\__init__.py
type nul > agent\config\settings.py
type nul > agent\config\constants.py
type nul > agent\config\thresholds.py

REM Root __init__.py
type nul > agent\__init__.py

echo ============================================
echo Agent Folder Structure Created Successfully
echo ============================================

pause
